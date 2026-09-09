import sys, os
os.environ['MEDITRIAGE_JWT_SECRET'] = 'test-secret'
os.environ['IMAGE_ENC_KEY'] = 'EXl15PqU2BVG_SSlFwCR0Q2npQTsVyULJO1018CS0Qc='
os.environ['FIELD_ENC_KEY'] = 'b51b2258bb42854b22a4cb0c867a201f4d06c9a49ce7874a03b6aa669137f39f'
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

import app as flask_app

# Verify route map includes the new endpoints
rules = [str(r) for r in flask_app.app.url_map.iter_rules()]
assert any('/api/images/upload' in r for r in rules), 'upload route missing'
assert any('/api/images/' in r for r in rules), 'get_image route missing'

# Verify PatientImage model is registered
with flask_app.app.app_context():
    from sqlalchemy import inspect
    insp = inspect(flask_app.db.engine)
    tables = insp.get_table_names()
    assert 'patient_images' in tables, f'patient_images table missing; got {tables}'

print('OK - app loaded, routes registered, DB table created')
print('Routes:', [r for r in rules if '/api/' in r])
