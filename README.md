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

The planner checks the forecast for the parsed hiking date and start position using the Open-Meteo API. Forecasts are available from today through 15 days ahead and do not require an API key. When the user asks to avoid mud and rain is forecast, the weather agent enriches the route preferences by avoiding unpaved paths.

Route maps use the original OSM way geometry when it is present on a `CONNECTED_TO` relationship, rather than drawing straight lines between graph nodes. After updating the importer, rerun the graph upload from `scratch/readosm.ipynb` so existing Neo4j relationships receive their `geometry` property. Routes from older data continue to render with node-to-node fallback lines.