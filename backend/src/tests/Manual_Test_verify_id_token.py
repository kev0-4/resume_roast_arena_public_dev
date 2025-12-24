
'''
This file has functions to verify idToken received from frotend to its native fields like uuid, email etc etc
this file also initializes firebase admin sdk with service account json
TO GET MANUAL TOKEN RUN THAT V0 APP THAT SHOWS ID TOKEN YOU MADE 
ONE SAMPLE TOKEN AT LAST LINE
'''
import firebase_admin
from firebase_admin import credentials, auth

SERVICE_ACCOUNT_KEY_PATH ="service-account.json"
try:
    cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
    firebase_admin.initialize_app(cred)
except FileNotFoundError as e:
    print("-----\n-----\n----\n Service accoutn json File Not Found \n-----\n-----\n----- ")
except Exception as e:
    print(f"-----\n-----\n----\n Error During firebase admin initialization:\n {e}\n-----\n-----\n----- ")

def verify_id_token(id_token):
    if not id_token:
        print(f"id_token is invalid/empty: {id_token}")
        return None
    try:
        decode_token = auth.verify_id_token(id_token)
        decoded_claims = decode_token
        uid =  decode_token.get('uid')
        email = decode_token.get('email')
        print(f"Token successfully verified for UID: {uid}, Email: {email}")
        return {
            "uid": decoded_claims["uid"],
            "email": decoded_claims.get("email"),
            "email_verified": decoded_claims.get("email_verified", False),
            "display_name": decoded_claims.get("name"),
            "picture": decoded_claims.get("picture"),
            "is_anonymous": decoded_claims.get("firebase", {}).get("sign_in_provider") == "anonymous"
        }
    except auth.InvalidIdTokenError as e:
        print(f"Verification failed: Invalid ID Token. Error: {e}")
        return None
    except Exception as e:
        print(f"An unexpeceted error occured during decoding of token: {e}")
        return None

print(verify_id_token("eyJhbGciOiJSUzI1NiIsImtpZCI6IjM4MTFiMDdmMjhiODQxZjRiNDllNDgyNTg1ZmQ2NmQ1NWUzOGRiNWQiLCJ0eXAiOiJKV1QifQ.eyJuYW1lIjoiVGFuZG9uIiwicGljdHVyZSI6Imh0dHBzOi8vbGgzLmdvb2dsZXVzZXJjb250ZW50LmNvbS9hL0FDZzhvY0tKR1ZiTk0tZDJGeUtUUnRZdDc3Y25EVE8tUU1McHE3NDdzUVgwSVdCQzRYbFBxN05xPXM5Ni1jIiwiaXNzIjoiaHR0cHM6Ly9zZWN1cmV0b2tlbi5nb29nbGUuY29tL3Jlc3VtZS1yb2FzdC1hcmVuYSIsImF1ZCI6InJlc3VtZS1yb2FzdC1hcmVuYSIsImF1dGhfdGltZSI6MTc2NTY5NTc5NCwidXNlcl9pZCI6Imc4WWZLT0JGekZPMFNuSnZLQUNVdEhSd1dsTjIiLCJzdWIiOiJnOFlmS09CRnpGTzBTbkp2S0FDVXRIUndXbE4yIiwiaWF0IjoxNzY1Njk1Nzk0LCJleHAiOjE3NjU2OTkzOTQsImVtYWlsIjoia3RhbmRvbjIwMDRAZ21haWwuY29tIiwiZW1haWxfdmVyaWZpZWQiOnRydWUsImZpcmViYXNlIjp7ImlkZW50aXRpZXMiOnsiZ29vZ2xlLmNvbSI6WyIxMTMxOTMzOTIwMDUyODI5ODk0MzciXSwiZW1haWwiOlsia3RhbmRvbjIwMDRAZ21haWwuY29tIl19LCJzaWduX2luX3Byb3ZpZGVyIjoiZ29vZ2xlLmNvbSJ9fQ.TCgEs6vgb5E9H35pQrMUwDGiv_rGeGPZ8QSAcO52EDhhveu3eT1Aze-2_XBAvKSEdgf5U2CA_LxWlvjFMCCCRFjESQOGT2-S_rHjLI7MmmV56jT2qR04Tqoo_rOkumLlwE6Q7WxjTtB9A_LZ9CNQlG091stKLfkP31pm6rFk-RA7HXQ9zbUCpTbWcAvuW679WjdlBWlBHXbnQF2t6_obqMkyCAeCv_kpfksq4URKFumThMgmgkmjrE0C0MeKFbJ0UI_aeKoiBi7MT4qbahgmgjY2eQa553oxe-Z0u9Vq8IIBXvyffE-5mpT4orWm3McHAYBDfbwWEFB7I4ZTuxV2Ug"))



print(verify_id_token("eyJhbGciOiJSUzI1NiIsImtpZCI6IjM4MTFiMDdmMjhiODQxZjRiNDllNDgyNTg1ZmQ2NmQ1NWUzOGRiNWQiLCJ0eXAiOiJKV1QifQ.eyJuYW1lIjoiS2V2aW4uVGFuZG9uIEJ0ZWNoMjAyMiIsInBpY3R1cmUiOiJodHRwczovL2xoMy5nb29nbGV1c2VyY29udGVudC5jb20vYS9BQ2c4b2NKNi1wLVQ0bW9zUmltNzYyV2xjTXM4YThuZ2w3czl5WkszTUNZeXpJMll0UjFBYm85ej1zOTYtYyIsImlzcyI6Imh0dHBzOi8vc2VjdXJldG9rZW4uZ29vZ2xlLmNvbS9yZXN1bWUtcm9hc3QtYXJlbmEiLCJhdWQiOiJyZXN1bWUtcm9hc3QtYXJlbmEiLCJhdXRoX3RpbWUiOjE3NjU2OTU5MDgsInVzZXJfaWQiOiIyVlJYS3BQZDNlWmo1T2RFZVpwRGNjQVg0bWwyIiwic3ViIjoiMlZSWEtwUGQzZVpqNU9kRWVacERjY0FYNG1sMiIsImlhdCI6MTc2NTY5NTkwOCwiZXhwIjoxNzY1Njk5NTA4LCJlbWFpbCI6ImtldmluLnRhbmRvbi5idGVjaDIwMjJAc2l0cHVuZS5lZHUuaW4iLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiZmlyZWJhc2UiOnsiaWRlbnRpdGllcyI6eyJnb29nbGUuY29tIjpbIjExNjEwMTg0ODM2MzMzNzAyMzE4NSJdLCJlbWFpbCI6WyJrZXZpbi50YW5kb24uYnRlY2gyMDIyQHNpdHB1bmUuZWR1LmluIl19LCJzaWduX2luX3Byb3ZpZGVyIjoiZ29vZ2xlLmNvbSJ9fQ.aW6hJ8nQoUej0U1v9RVRpVmfJzNqHCNlYtiHVnaf4hRw7kk6vn6bun4WIDh4WW_0Drq4mYg6IdPa4VyGvc6Baf9-4g3CvhgVy6a_P7rkXkUWj6gLi549aCruJ88-FmmFqHUBObMUUGoyTEcvUleWI_azEa0NAfCmmTtf2jP2zH0QzytKy6lVApojQ1aK6q5hZQZpak3NFR7TmiXS9ZSEjtNZxO9HVq8-Vix6AUZ4SCOzB0aUmV3FeO7WFiTxtjy9oNsasYSpzzD_jiAKMAYKJ0GnSJJ5xpFq38MOQuQhsWyPzSmFW5gbukTow0dnWZeDaYb5uVrBZjeW7GS1Lv6nZQ"))