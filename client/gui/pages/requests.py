from datetime import datetime
from math import floor

from dash import register_page, Input, Output, callback
from dash.html import Div, Button
from dash.dash_table import DataTable

from pandas import DataFrame

from model import Request, Attempt, CoS


register_page(__name__, path='/', redirect_from=['/requests'],
              name='Requests', title='Requests')

cos_names = {cos[0]: cos[1] 
             for cos in CoS.select(fields=('id', 'name'), as_obj=False)}

cols = list(Request.columns())
for i, col in enumerate(cols):
    if col == 'id':
        cols[i] = 'ID'
    elif col == 'cos_id':
        cols[i] = 'CoS'
    elif col == 'hreq_at':
        cols[i] = 'Start'
    elif col == 'dres_at':
        cols[i] = 'Finish'
    else:
        cols[i] = col.capitalize()
cols.extend(['Time (ms)', 'Attempts'])

PAGE_SIZE = 15


def get_data(page):
    requests = Request.select_page(page, PAGE_SIZE, orders=('hreq_at',),
                                   as_obj=False)
    for row in requests:
        start = finish = attempts = 0
        for i, col in enumerate(cols):
            if col == 'ID':
                attempts = Attempt.select(fields=('count(*)',), as_obj=False,
                                          req_id=('=', row[i]))[0][0]
            elif col == 'CoS':
                row[i] = cos_names[row[i]]
            elif col == 'Data' or col == 'Result':
                row[i] = row[i].decode() if row[i] else None
            elif col == 'State':
                row[i] = Request._states[row[i]]
            elif col == 'Start':
                start = row[i]
                row[i] = datetime.fromtimestamp(row[i]) if row[i] else None
            elif col == 'Finish':
                finish = row[i]
                row[i] = datetime.fromtimestamp(row[i]) if row[i] else None
        row.extend([
            round((finish - start) * 1000, 2) if finish else None,
            attempts
        ])

    _count = Request.select(fields=('count(*)',),
                            as_obj=False)[0][0] / PAGE_SIZE
    count = floor(_count)

    return (DataFrame(requests, columns=cols).to_dict('records'),
            count + 1 if count < _count else count)


layout = Div(className='page reduced-left', children=[
    Div(className='page-content', children=[
        Button('Refresh', id='refresh-btn', n_clicks=0),
        DataTable(id='requests-tbl', page_current=0, page_action='custom',
                  page_size=PAGE_SIZE, style_table={'max_width': '100vw'}),
    ])

])


@callback(
    Output('requests-tbl', 'data'),
    Output('requests-tbl', 'page_count'),
    Input('requests-tbl', 'page_current'),
    Input('refresh-btn', 'n_clicks'))
def _update_table(page_current, _):
    return get_data(page_current + 1)
