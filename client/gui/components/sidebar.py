from dash import page_registry
from dash.html import Div, Span
from dash.dcc import Link


_icons = {
    'Requests': 'fa-arrow-right-from-bracket',
    'Attempts': 'fa-arrow-rotate-right',
    'Responses': 'fa-arrow-right-to-bracket',
}


def _icon(name):
    try:
        return _icons[name]
    except:
        return ''


def sidebar():
    return (
        Div(className='sidebar sidebar-unlocked', children=[
            item(page) for page in page_registry.values()
        ])
    )


def item(page):
    return (
        Div(className='item', children=[
            Link(href=page['relative_path'], children=[
                Div(className='item-icon', children=[
                    Span(className='fas fa-solid ' + _icon(page['name']) +
                         ' fa-lg center-vertical center-horizontal')
                ]),
                Span(page['name'],
                     className='item-title truncate-one center-vertical')
            ])
        ])
    )
