from dash import register_page
from dash.html import Div


register_page(__name__, path='/attempts', name='Attempts', title='Attempts')


layout = Div(className='page reduced-left', children=[
    Div(className='page-content', children='''
        This is our Attempts page content.
    '''),

])
