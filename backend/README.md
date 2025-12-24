kevin@kevin-elitebook:~/Desktop/resume_roast_arena$ alembic revision --autogenerate -m "ADDED EXTRACTED toENUM sessions"


kevin@kevin-elitebook:~/Desktop/resume_roast_arena$ alembic upgrade head



kevin@kevin-elitebook:~/Desktop/resume_roast_arena$ uvicorn app:app --reload