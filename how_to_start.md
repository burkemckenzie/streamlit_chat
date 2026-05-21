cd /Users/burkemckenzie/Documents/streamlit_chat
deactivate 2>/dev/null; true
rm -rf venv
python3 -m venv venv
touch venv/.metadata_never_index
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py