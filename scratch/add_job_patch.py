with open('app/api/main.py', 'r', encoding='utf-8') as f:
    c = f.read()

old_get_job = '''    @app.get("/jobs/{job_id}", dependencies=[Depends(recruiter)])
    def get_job(job_id: int, db=Depends(get_db)):
        j = db.get(Job, job_id)
        if not j:
            raise NotFound("job not found")
        return {"id": j.id, "title": j.title, "description": j.description, "competencies": jload(j.competencies_json, [])}'''

new_get_job = '''    @app.get("/jobs/{job_id}", dependencies=[Depends(recruiter)])
    def get_job(job_id: int, db=Depends(get_db)):
        j = db.get(Job, job_id)
        if not j:
            raise NotFound("job not found")
        return {"id": j.id, "title": j.title, "description": j.description, "competencies": jload(j.competencies_json, [])}

    class JobUpdateIn(BaseModel):
        title: Optional[str] = None
        description: Optional[str] = None

    @app.patch("/jobs/{job_id}", dependencies=[Depends(recruiter)])
    def update_job(job_id: int, body: JobUpdateIn, db=Depends(get_db)):
        j = db.get(Job, job_id)
        if not j:
            raise NotFound("job not found")
        if body.title is not None and body.title.strip():
            j.title = body.title.strip()
        if body.description is not None:
            j.description = body.description.strip()
        db.commit()
        return {"id": j.id, "title": j.title, "description": j.description}'''

assert old_get_job in c, 'old_get_job not found in app/api/main.py'
c = c.replace(old_get_job, new_get_job)
with open('app/api/main.py', 'w', encoding='utf-8') as f:
    f.write(c)
print('Successfully added PATCH /jobs/{job_id} to app/api/main.py')
