🚀 GenAI Sanction Notesheet Generator
⚡ Automating ONGC-Style Technical Documentation with AI

Transforming manual sanction note preparation into an intelligent, automated workflow using Generative AI + NLP.

🧩 What is this?

This project is a full-stack AI-powered system that generates formal sanction notesheets used in enterprise environments (like ONGC).

Instead of writing long technical documents manually, this tool:
👉 Takes structured inputs + PDFs
👉 Understands the data using NLP
👉 Generates a complete 10-section professional note instantly

✨ Core Highlights

🔹 🧠 GenAI-Powered Writing – Uses LLM (LLaMA 3 via Groq)
🔹 📄 PDF Intelligence – Extracts specs & vendor pricing from GeM files
🔹 📊 Multi-Item Processing – Handles complex procurement scenarios
🔹 🏢 Industry Workflow Simulation – Designed based on real ONGC processes
🔹 💾 Database Integration – Stores structured records in MySQL
🔹 📥 Export Ready – Download notes as formatted Word documents

🏗️ System Flow
User Input → Data Processing → PDF Extraction → LLM Generation → Structured Note → Export
🛠️ Tech Stack
👨‍💻 Backend
Python (Flask)
Groq API (LLaMA 3.3 – 70B)
🎨 Frontend
HTML + CSS + JavaScript
🧠 AI & Data
NLP Processing
Regex-based extraction
pdfplumber
🗄️ Database
MySQL
📂 Project Structure
GenAI-Sanction-Notesheet/
│── app.py              # Backend logic + AI integration
│── index.html          # Frontend UI
│── requirements.txt    # Dependencies
│── .env                # API key (not included)
⚙️ How It Works
🪜 Step-by-Step

1️⃣ Enter procurement details (MATCODE, LPR, GeM, etc.)
2️⃣ Add subject & justification
3️⃣ Upload GeM PDF (optional but powerful 💡)
4️⃣ Click Generate

💥 Boom → AI creates a fully structured sanction note with:

Introduction
Infrastructure
Financial Table
Technical Specs
Approval Section
🔑 Setup Guide
1️⃣ Clone Repo
git clone https://github.com/your-username/GenAI-Sanction-Notesheet.git
cd GenAI-Sanction-Notesheet
2️⃣ Install Dependencies
pip install -r requirements.txt
3️⃣ Add API Key

Create .env file:

GROQ_API_KEY=your_api_key_here
4️⃣ Run App
python app.py

🌐 Open → http://localhost:5000

📊 What Makes It Powerful?

✔️ Converts unstructured + semi-structured data → formal documents
✔️ Reduces manual effort & human error
✔️ Mimics real enterprise documentation standards
✔️ Combines AI + Backend + Frontend + Database in one system

🎯 Use Cases

🏢 Enterprise procurement automation
📄 Government/PSU documentation
📊 Contract & vendor analysis
🤖 AI-based workflow automation systems

🔮 Future Scope

🚀 Role-based dashboards
🌍 Multi-language support
☁️ Cloud deployment (AWS/Azure)
🔗 ERP/SAP integration
📊 Advanced analytics dashboard

👩‍💻 Author

Darshana P
🎓 B.Tech – AI & Data Science
💡 Passionate about AI, Automation & Real-world Problem Solving

⭐ Final Note

This project reflects how Generative AI can move beyond chatbots and actually solve real industry problems.
