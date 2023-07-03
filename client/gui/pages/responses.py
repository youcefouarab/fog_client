from dash import register_page
from dash.html import Div


register_page(__name__, path='/responses', name='Responses', title='Responses')


layout = Div(className='page reduced-left', children=[
    Div(className='page-content', children='''
        This is our Responses page content.
    '''),

])
