# AI Trail Planner

## Streamlit app

Install the Streamlit dependency in the project virtual environment:

```powershell
pip install -r requirements-streamlit.txt
```

Start the app from the repository root:

```powershell
streamlit run app/app.py
```

The app uses the Neo4j and Google settings from `.env`. It runs each trail request in a background worker, embeds the generated map, and shows the route intent extracted by the planner.