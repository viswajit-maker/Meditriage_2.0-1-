import os
import sys
import uuid
import io
import json
import sqlite3
import piexif
from PIL import Image as PilImage
from datetime import datetime, timezone, timedelta

# Mock env vars for test
os.environ['MEDITRIAGE_JWT_SECRET'] = 'test-secret'
os.environ['IMAGE_ENC_KEY'] = 'EXl15PqU2BVG_SSlFwCR0Q2npQTsVyULJO1018CS0Qc='
os.environ['FIELD_ENC_KEY'] = 'b51b2258bb42854b22a4cb0c867a201f4d06c9a49ce7874a03b6aa669137f39f'

# Ensure we're in the backend dir
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from app import (
    app, db, User, Patient, PatientImage, Consent, AccessLog, 
    _image_cipher, purge_old_data, IMAGE_STORE, DB_PATH
)

app.config['TESTING'] = True
client = app.test_client()

with app.app_context():
    db.drop_all()
    db.create_all()

def test_runner():
    failures = []
    
    with app.app_context():
        # Setup users
        patient_user = User(email='patient@test.com', password_hash='hash', role='patient')
        doctor_user = User(email='doctor@test.com', password_hash='hash', role='doctor')
        doctor2_user = User(email='doctor2@test.com', password_hash='hash', role='doctor')
        hosp_user = User(email='hosp@test.com', password_hash='hash', role='hospital_booking')
        db.session.add_all([patient_user, doctor_user, doctor2_user, hosp_user])
        db.session.commit()
        
        # Setup patient
        patient = Patient(
            id=patient_user.id,
            age=30, gender='Male',
            name='Secret John', phone='1234567890', symptoms='Chest pain',
            assigned_doctor_id=doctor_user.id
        )
        db.session.add(patient)
        # Setup consent
        consent = Consent(patient_id=patient.id, purpose='medical_triage', consent_version='1.0')
        db.session.add(consent)
        db.session.commit()

        # Generate tokens
        from flask_jwt_extended import create_access_token
        doc_token = create_access_token(identity=doctor_user.id, additional_claims={'role': 'doctor'})
        doc2_token = create_access_token(identity=doctor2_user.id, additional_claims={'role': 'doctor'})
        hosp_token = create_access_token(identity=hosp_user.id, additional_claims={'role': 'hospital_booking'})
        pat_token = create_access_token(identity=patient_user.id, additional_claims={'role': 'patient'})

        # ---------------------------------------------------------
        # Test 1: Upload a test image with GPS EXIF data
        # ---------------------------------------------------------
        try:
            # Create an image with fake EXIF
            img = PilImage.new('RGB', (100, 100), color='red')
            exif_dict = {"GPS": {piexif.GPSIFD.GPSLatitude: ((10, 1), (20, 1), (30, 1))}}
            exif_bytes = piexif.dump(exif_dict)
            buf = io.BytesIO()
            img.save(buf, format='JPEG', exif=exif_bytes)
            buf.seek(0)
            
            # Consent first (for Test 6 context, but since we didn't implement it yet, it might succeed anyway)
            # Actually upload_image takes a file
            resp = client.post('/api/images/upload', data={
                'image': (buf, 'test.jpg'),
                'patient_id': patient.id
            }, content_type='multipart/form-data')
            
            if resp.status_code != 201:
                failures.append(f"T1 Failed to upload image: {resp.status_code} {resp.text}")
            else:
                img_id = resp.json['image_id']
                # Check direct file EXIF
                blob_path = IMAGE_STORE / f"{img_id}.enc"
                decrypted = _image_cipher().decrypt(blob_path.read_bytes())
                dec_img = PilImage.open(io.BytesIO(decrypted))
                
                # piexif.load will fail if there's no EXIF, or return empty
                has_exif = False
                try:
                    loaded_exif = piexif.load(dec_img.info.get("exif", b""))
                    if loaded_exif and 'GPS' in loaded_exif and loaded_exif['GPS']:
                        has_exif = True
                except Exception:
                    pass
                if has_exif:
                    failures.append("T1 EXIF data survived encryption pipeline!")
                else:
                    print("T1 passed: EXIF stripped.")
        except Exception as e:
            failures.append(f"T1 Exception: {e}")

        # ---------------------------------------------------------
        # Test 2: Try uploading .exe renamed to .jpg
        # ---------------------------------------------------------
        try:
            fake_exe = io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00")
            resp = client.post('/api/images/upload', data={
                'image': (fake_exe, 'malware.jpg'),
                'patient_id': patient.id
            }, content_type='multipart/form-data')
            if resp.status_code != 415:
                failures.append(f"T2 Magic byte check failed. Expected 415, got {resp.status_code}")
            else:
                print("T2 passed: Magic byte check rejected fake JPG.")
        except Exception as e:
            failures.append(f"T2 Exception: {e}")

        # ---------------------------------------------------------
        # Test 3: Query raw database file directly
        # ---------------------------------------------------------
        try:
            db.session.commit() # ensure flushed
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM patients WHERE id=?", (patient.id,))
            row = cursor.fetchone()
            if not row:
                failures.append("T3 Patient row not found in raw DB!")
            else:
                row_str = str(row)
                if 'Secret John' in row_str or '1234567890' in row_str or 'Chest pain' in row_str:
                    failures.append("T3 Plaintext data found in SQLite DB!")
                else:
                    print("T3 passed: No plaintext sensitive fields in DB.")
            conn.close()
        except Exception as e:
            failures.append(f"T3 Exception: {e}")

        # ---------------------------------------------------------
        # Test 4: Doctor account fetch patient not assigned
        # ---------------------------------------------------------
        try:
            resp = client.get(f'/api/doctor/patient/{patient.id}', headers={'Authorization': f'Bearer {doc2_token}'})
            if resp.status_code != 403:
                failures.append(f"T4 Expected 403 for unauthorized doctor, got {resp.status_code}")
            else:
                print("T4 passed: Unassigned doctor access blocked.")
        except Exception as e:
            failures.append(f"T4 Exception: {e}")

        # ---------------------------------------------------------
        # Test 5: Hospital booking endpoint missing symptoms/images
        # ---------------------------------------------------------
        try:
            resp = client.get(f'/api/booking/patient/{patient.id}', headers={'Authorization': f'Bearer {hosp_token}'})
            if resp.status_code != 200:
                failures.append(f"T5 Expected 200 for hospital booking, got {resp.status_code}")
            else:
                data = resp.json
                if 'symptoms' in data or 'image' in data:
                    failures.append(f"T5 Hospital booking returned restricted fields: {data.keys()}")
                else:
                    print("T5 passed: Hospital booking endpoint excluded restricted fields.")
        except Exception as e:
            failures.append(f"T5 Exception: {e}")

        # ---------------------------------------------------------
        # Test 6: Submit photo without checking consent
        # ---------------------------------------------------------
        try:
            # Create a new patient without consent
            no_consent_id = str(uuid.uuid4())
            buf = io.BytesIO(b"dummy")
            resp = client.post('/api/images/upload', data={
                'image': (buf, 'test.jpg'),
                'patient_id': no_consent_id
            }, content_type='multipart/form-data')
            
            # Since upload_image currently doesn't check consent, this might fail the test (return 415 or 422 because it's not a real image, but not 403/400 for consent)
            # Let's send a valid image to be sure
            img = PilImage.new('RGB', (10, 10), color='blue')
            buf = io.BytesIO()
            img.save(buf, format='JPEG')
            buf.seek(0)
            resp = client.post('/api/images/upload', data={
                'image': (buf, 'test2.jpg'),
                'patient_id': no_consent_id
            }, content_type='multipart/form-data')
            
            if resp.status_code == 201:
                failures.append(f"T6 Upload succeeded without consent! Expected rejection (e.g. 403).")
            else:
                print("T6 passed: Upload rejected without consent.")
        except Exception as e:
            failures.append(f"T6 Exception: {e}")

        # ---------------------------------------------------------
        # Test 7: Check AccessLog table after doctor views
        # ---------------------------------------------------------
        try:
            # Legitimate read
            client.get(f'/api/doctor/patient/{patient.id}', headers={'Authorization': f'Bearer {doc_token}'})
            logs = AccessLog.query.filter_by(actor_id=doctor_user.id).all()
            if not logs:
                failures.append("T7 No access logs found for doctor view.")
            else:
                log = logs[0]
                if 'Chest pain' in log.action or 'Secret John' in log.resource_id:
                     failures.append("T7 Access log contains sensitive data!")
                else:
                     print("T7 passed: Access log generated securely.")
        except Exception as e:
            failures.append(f"T7 Exception: {e}")

        # ---------------------------------------------------------
        # Test 8: Retention purge job
        # ---------------------------------------------------------
        try:
            img = PatientImage(id=str(uuid.uuid4()), patient_id=patient.id, uploaded_at=datetime.now(timezone.utc) - timedelta(days=95), retention_hold=False)
            db.session.add(img)
            db.session.commit()
            
            # create dummy blob
            blob_path = IMAGE_STORE / f"{img.id}.enc"
            blob_path.write_bytes(b"dummy_encrypted_data")
            
            cutoff = datetime.now(timezone.utc) - timedelta(days=90)
            print("Cutoff:", cutoff)
            print("Img uploaded_at:", img.uploaded_at)
            
            from app import app as flask_app
            with flask_app.app_context():
                res = PatientImage.query.filter(
                    PatientImage.uploaded_at < cutoff,
                    PatientImage.retention_hold == False
                ).all()
                print("Query with retention_hold:", res)

            purge_old_data()
            
            from app import db as flask_db
            with flask_app.app_context():
                # Need to expire/refresh if checking same session
                flask_db.session.expire_all()
                still_exists = flask_db.session.get(PatientImage, img.id)
                print("Still exists in DB?", still_exists)
                print("File exists?", blob_path.exists())
            
            if still_exists or blob_path.exists():
                failures.append("T8 Purge job failed to delete old record or file.")
            else:
                print("T8 passed: Purge job successfully deleted old data.")
        except Exception as e:
            failures.append(f"T8 Exception: {e}")

    return failures

if __name__ == '__main__':
    fails = test_runner()
    if fails:
        print("\nFAILURES:")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    else:
        print("\nAll 8 end-to-end tests passed successfully.")
