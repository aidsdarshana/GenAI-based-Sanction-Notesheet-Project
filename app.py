import os
import re
import json
import tempfile
import time
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import pymysql
from datetime import datetime
from dotenv import load_dotenv
from groq import Groq
import pdfplumber
import io

load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# ========== MySQL Configuration ==========
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'ongc_sanction',
    'charset': 'utf8mb4'
}

# ========== Groq Configuration ==========
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("❌ GROQ_API_KEY not found. Set it in .env file.")
    client = None
else:
    client = Groq(api_key=GROQ_API_KEY)
GROQ_MODEL = "llama-3.3-70b-versatile"

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

def save_to_database(data):
    connection = None
    try:
        connection = pymysql.connect(**DB_CONFIG)
        cursor = connection.cursor()
        sql_note = """
            INSERT INTO sanction_notes (
                subject, justification, pr_number, release_strategy
            ) VALUES (%s, %s, %s, %s)
        """
        cursor.execute(sql_note, (
            data.get('subject'),
            data.get('justification'),
            data.get('prNumber') or None,
            data.get('releaseStrategy') or None
        ))
        note_id = cursor.lastrowid
        sql_item = """
            INSERT INTO sanction_items (
                sanction_note_id, item_code, material_type,
                lpr_status, lpr_po_number, lpr_po_date, lpr_unit_price,
                gem_status, gem_l1_rate, gem_unit_price, gem_file
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        for it in data.get('items', []):
            gem_file_blob = it.get('gem_file_blob') if it.get('gem_file_blob') else None
            cursor.execute(sql_item, (
                note_id,
                it.get('itemCode'),
                it.get('matType'),
                it.get('lprStatus'),
                it.get('lprPo') or None,
                it.get('lprDate') or None,
                float(it.get('lprAmount')) if it.get('lprAmount') else None,
                it.get('gemStatus'),
                float(it.get('gemL1')) if it.get('gemL1') else None,
                float(it.get('gemUnit')) if it.get('gemUnit') else None,
                gem_file_blob
            ))
        connection.commit()
        print(f"✅ Saved to DB: note {note_id}")
    except Exception as e:
        print(f"⚠️ DB save skipped: {e}")
    finally:
        if connection:
            connection.close()

# ----- PDF extraction functions (unchanged) -----
def extract_pdf_with_llm(pdf_text):
    if not client:
        return {}, []
    prompt = f"""You are an AI assistant that extracts technical specifications and vendor price information from GeM PDF documents.

Extract:
1. A dictionary of technical specifications (key-value pairs) – only hardware/performance specs.
2. A list of vendors with their offered prices (numeric, remove commas).

Output ONLY valid JSON with keys: "specifications" (object) and "vendors" (array of objects with "name" and "price").

PDF Text (first 4000 characters):
{pdf_text[:4000]}

JSON:
"""
    try:
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=GROQ_MODEL,
            temperature=0.1,
            max_tokens=1000,
            response_format={"type": "json_object"}
        )
        result = json.loads(chat.choices[0].message.content)
        specs = result.get("specifications", {})
        vendors = result.get("vendors", [])
        return specs, vendors
    except Exception as e:
        print(f"LLM extraction failed: {e}")
        return {}, []

def extract_pdf_fallback(pdf_text):
    specs = {}
    keywords = {
        "Form Factor": r"Form Factor\s*\(RU\)\s*(\d+)",
        "Throughput (Mbps)": r"Throughput with all features enabled.*?(\d+)",
        "Concurrent Sessions": r"Concurrent Session.*?(\d+)K?",
        "Warranty (Years)": r"Warranty.*?(\d+)\s*Years?",
        "Certification": r"Certification\s*(.*?)(?:\n|$)"
    }
    for key, pattern in keywords.items():
        match = re.search(pattern, pdf_text, re.IGNORECASE)
        if match:
            specs[key] = match.group(1).strip()
    vendors = []
    price_pattern = r"(Palo Alto Networks|FORTINET|Sonicwall|Sophos|NUMERIC|CyberPower|hp|Unison).*?₹\s*([\d,]+\.\d{2})"
    matches = re.findall(price_pattern, pdf_text, re.IGNORECASE)
    seen = set()
    for brand, price in matches:
        if brand not in seen:
            vendors.append({"name": brand.strip(), "price": price.replace(",", "")})
            seen.add(brand)
    if not vendors:
        offer_matches = re.findall(r"Offer Price/Unit[:\s]*₹\s*([\d,]+\.\d{2})", pdf_text)
        if offer_matches:
            vendors.append({"name": "OEM", "price": offer_matches[0].replace(",", "")})
    return specs, vendors

def extract_pdf_info(pdf_content):
    if not pdf_content:
        return {}, []
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            tmp.write(pdf_content)
            tmp_path = tmp.name
        with pdfplumber.open(tmp_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text() or ""
                full_text += text + "\n"
        specs, vendors = extract_pdf_with_llm(full_text)
        if not specs and not vendors:
            specs, vendors = extract_pdf_fallback(full_text)
        return specs, vendors
    except Exception as e:
        print(f"PDF processing error: {e}")
        return {}, []
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except:
                pass

# ----- Post‑processing to fix structure -----
def fix_structure(raw_text):
    """Ensure each section title is on its own line and followed by a blank line."""
    # Ensure starts with **SANCTION NOTE**
    if not raw_text.strip().startswith("**SANCTION NOTE**"):
        if "**SANCTION NOTE**" in raw_text:
            raw_text = raw_text.split("**SANCTION NOTE**", 1)[1]
            raw_text = "**SANCTION NOTE**" + raw_text
        else:
            raw_text = "**SANCTION NOTE**\n\n" + raw_text
    
    # Split into lines
    lines = raw_text.split('\n')
    fixed_lines = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        # If line is a section title like **1. Introduction**
        if re.match(r'^\*\*\d+\.', stripped):
            # Ensure previous line is not already a blank line
            if fixed_lines and fixed_lines[-1].strip() != '':
                fixed_lines.append('')
            fixed_lines.append(line)
        elif stripped == '':
            fixed_lines.append(line)
        else:
            fixed_lines.append(line)
    
    # Join and clean up multiple blank lines
    fixed_text = '\n'.join(fixed_lines)
    fixed_text = re.sub(r'\n{3,}', '\n\n', fixed_text)
    return fixed_text

def markdown_table_to_html(markdown_table):
    lines = markdown_table.strip().split('\n')
    if len(lines) < 2:
        return markdown_table
    header_sep_index = None
    for i, line in enumerate(lines):
        if re.match(r'[\s\|]*[-:]+[\s\|]*', line):
            header_sep_index = i
            break
    if header_sep_index is None:
        return markdown_table
    headers = [cell.strip() for cell in lines[0].split('|')[1:-1]]
    rows = []
    for line in lines[header_sep_index+1:]:
        if line.strip():
            cells = [cell.strip() for cell in line.split('|')[1:-1]]
            rows.append(cells)
    html = '<table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%;">'
    html += '<thead><tr>' + ''.join(f'<th style="background-color: #f2f2f2;">{h}</th>' for h in headers) + '</tr></thead>'
    html += '<tbody>'
    for row in rows:
        html += '<tr>' + ''.join(f'<td>{cell}</td>' for cell in row) + '</tr>'
    html += '</tbody></table>'
    return html

def convert_note_to_html(note_text):
    """Convert the fixed markdown note to clean HTML with proper spacing."""
    # First, fix the structure
    note_text = fix_structure(note_text)
    
    # Replace markdown bold with HTML strong
    note_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', note_text)
    
    # Process line by line to build HTML blocks
    lines = note_text.split('\n')
    html_parts = []
    in_table = False
    table_lines = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            html_parts.append('<br>')
            i += 1
            continue
        
        # Check if line is a section title (e.g., <strong>1. Introduction</strong>)
        if re.match(r'<strong>\d+\.', line):
            # Wrap in <h3> for section titles
            # Extract the text inside strong
            title_text = re.sub(r'</?strong>', '', line)
            html_parts.append(f'<h3>{title_text}</h3>')
            i += 1
            continue
        
        # Check for table start (line starts with |)
        if line.startswith('|') and not in_table:
            in_table = True
            table_lines = [lines[i]]
            i += 1
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i])
                i += 1
            # Convert collected table lines
            table_md = '\n'.join(table_lines)
            html_table = markdown_table_to_html(table_md)
            html_parts.append(html_table)
            in_table = False
            continue
        
        # Normal paragraph: wrap in <p>
        # But if the line is not empty and not a heading or table
        if line and not line.startswith('<table'):
            html_parts.append(f'<p>{line}</p>')
            i += 1
        else:
            i += 1
    
    return '\n'.join(html_parts)

@app.route('/generate', methods=['POST'])
def generate():
    try:
        if request.content_type and 'multipart/form-data' in request.content_type:
            subject = request.form.get('subject', '')
            justification = request.form.get('justification', '')
            pr_number = request.form.get('prNumber', 'Not yet raised')
            release_strategy = request.form.get('releaseStrategy', 'Not specified')
            items_json = request.form.get('items', '[]')
            items = json.loads(items_json)
            for idx, it in enumerate(items):
                if it.get('gemStatus') == 'yes':
                    file_key = f'gem_pdf_{idx}'
                    if file_key in request.files:
                        pdf_file = request.files[file_key]
                        if pdf_file and pdf_file.filename.endswith('.pdf'):
                            pdf_content = pdf_file.read()
                            it['gem_file_blob'] = pdf_content
                            specs, vendors = extract_pdf_info(pdf_content)
                            it['gem_specs'] = specs
                            it['gem_vendors'] = vendors
        else:
            data = request.json
            subject = data.get('subject', '')
            justification = data.get('justification', '')
            pr_number = data.get('prNumber', 'Not yet raised')
            release_strategy = data.get('releaseStrategy', 'Not specified')
            items = data.get('items', [])

        # Build items text
        items_text = ""
        for idx, it in enumerate(items, 1):
            items_text += f"- MATCODE: {it.get('itemCode')}\n"
            items_text += f"  Material Type: {it.get('matType')}\n"
            items_text += f"  Unit Price (₹): {it.get('lprAmount') or it.get('gemUnit') or 0}\n"
            items_text += f"  LPR Status: {it.get('lprStatus')}\n"
            items_text += f"  GeM Status: {it.get('gemStatus')}\n"
            if it.get('lprPo'):
                items_text += f"  PO Number: {it.get('lprPo')}\n"
            if it.get('lprDate'):
                items_text += f"  PO Date: {it.get('lprDate')}\n"
            if it.get('gem_specs'):
                items_text += "  Technical Specifications (from uploaded file):\n"
                for k, v in it.get('gem_specs').items():
                    items_text += f"    - {k}: {v}\n"
            if it.get('gem_vendors'):
                items_text += "  Budgetary Quotes from uploaded file:\n"
                for v in it.get('gem_vendors'):
                    items_text += f"    - Vendor: {v['name']}, Price: ₹{v['price']}\n"

        # Master prompt
        master_prompt = f"""You are a senior ONGC technical officer. Generate a long formal sanction note with the following 10 sections. 
CRITICAL: Each section title must be on its own line, followed by a blank line, then the content. 
Use exactly this format:

**SANCTION NOTE**

**Subject:** [subject text]

**1. Introduction**
[long content]

**2. Current Infrastructure**
(a) [first sub‑section]
[details]
(b) [second sub‑section if any]

**3. Objective**
[5-6 lines long content]

**4. Project**
(a) [first solution]
(b) [second solution]

**5. Warranty & AMC**
[5-6 lines long content]

**6. Financial Implication**
[markdown table with columns: Item Code, Material Type, LPR Status, GeM Status, Unit Price (₹), Technical Specification]

**7. Technical Specification**
[detailed from uploaded files]

**8. Requirement / Proposal**
[5-6 lines long content]

**9. Purchase Requisition & Approval**
PR Number: {pr_number}
Release Strategy: {release_strategy}

**10. Approval**
Submitted for kind approval.

Now use the following data. Correct spelling/grammar. Use ONLY provided items.

Subject: {subject}
Justification: {justification}

Items:
{items_text}
"""

        if not client:
            raise Exception("Groq client not initialized. Check GROQ_API_KEY in .env file.")

        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a senior ONGC technical officer. Generate perfect sanction notes. Never invent data. Use only provided information. Always leave a blank line between each section title and its content."},
                {"role": "user", "content": master_prompt}
            ],
            model=GROQ_MODEL,
            temperature=0.1,
            max_tokens=3000,
        )
        generated_text = chat_completion.choices[0].message.content

        # Post-process to fix any structural issues
        generated_text = fix_structure(generated_text)

        save_to_database({
            'subject': subject,
            'justification': justification,
            'prNumber': pr_number,
            'releaseStrategy': release_strategy,
            'items': items
        })

        app.last_note = generated_text
        return jsonify({"success": True, "note": generated_text})

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/download', methods=['GET'])
def download_note():
    if not hasattr(app, 'last_note') or not app.last_note:
        return jsonify({"error": "No note generated yet"}), 404

    note_text = app.last_note
    html_content = convert_note_to_html(note_text)

    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Sanction Note</title>
<style>
    @page {{
        size: A4;
        margin: 2.54cm;
    }}
    body {{
        font-family: 'Times New Roman', Times, serif;
        font-size: 12pt;
        line-height: 1.5;
        margin: 0;
        padding: 0;
        background: white;
    }}
    .container {{
        max-width: 100%;
        margin: 0 auto;
    }}
    h3 {{
        font-size: 14pt;
        font-weight: bold;
        margin-top: 1.2em;
        margin-bottom: 0.5em;
    }}
    p {{
        margin-bottom: 0.8em;
        text-align: justify;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        margin: 1em 0;
    }}
    th, td {{
        border: 1px solid #000000;
        padding: 6px 8px;
        vertical-align: top;
    }}
    th {{
        background-color: #f2f2f2;
        font-weight: bold;
        text-align: center;
    }}
    td {{
        text-align: left;
    }}
    strong {{
        font-weight: bold;
    }}
    br {{
        margin: 0.2em 0;
    }}
</style>
</head>
<body>
<div class="container">
{html_content}
</div>
</body>
</html>"""

    return send_file(
        io.BytesIO(full_html.encode('utf-8')),
        mimetype='application/msword',
        as_attachment=True,
        download_name='sanction_note.doc'
    )

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(debug=True)