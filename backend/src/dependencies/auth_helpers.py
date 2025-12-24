from fastapi import Request, HTTPException, status, Depends

def extract_token_from_request(request:Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = auth_header.split("Bearer ")[1]
    return token