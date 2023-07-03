from dash import Dash, page_container
from dash.html import Div

from components.sidebar import sidebar


app = Dash(__name__, use_pages=True)

app.layout = Div([
	page_container,
    sidebar()
])
