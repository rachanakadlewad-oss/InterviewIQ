# 1. Update app/services/scheduler.py
with open('app/services/scheduler.py', 'r', encoding='utf-8') as f:
    sc_txt = f.read()

old_load_add = '''        db.add(Slot(id=sid, resource=res, start=st, end=en))
        added += 1
    db.commit()'''

new_load_add = '''        db.add(Slot(id=sid, resource=res, start=st, end=en))
        db.flush()
        added += 1
    db.commit()'''

old_gen_add = '''                    db.add(Slot(id=sid, resource=res, start=start, end=end))
                    added += 1
            produced += 1'''

new_gen_add = '''                    db.add(Slot(id=sid, resource=res, start=start, end=end))
                    db.flush()
                    added += 1
            produced += 1'''

assert old_load_add in sc_txt, 'old_load_add not found'
assert old_gen_add in sc_txt, 'old_gen_add not found'

sc_txt = sc_txt.replace(old_load_add, new_load_add).replace(old_gen_add, new_gen_add)
with open('app/services/scheduler.py', 'w', encoding='utf-8') as f:
    f.write(sc_txt)
print('Updated app/services/scheduler.py')

# 2. Update frontend/iqui/views/interviews.py
with open('frontend/iqui/views/interviews.py', 'r', encoding='utf-8') as f:
    int_txt = f.read()

old_day_slots = '''            day_slots = [s for s in slots if s["start"].startswith(pick_day)]
            day_slots.sort(key=lambda s: (s["start"], s["resource"], s["id"]))'''

new_day_slots = '''            raw_day_slots = [s for s in slots if s["start"].startswith(pick_day)]
            dedup_map = {}
            for s in raw_day_slots:
                key = (s["resource"], s["start"], s["end"])
                if key not in dedup_map or (s.get("application_id") and not dedup_map[key].get("application_id")):
                    dedup_map[key] = s
            day_slots = list(dedup_map.values())
            day_slots.sort(key=lambda s: (s["start"], s["resource"], s["id"]))'''

assert old_day_slots in int_txt, 'old_day_slots not found'
int_txt = int_txt.replace(old_day_slots, new_day_slots)
with open('frontend/iqui/views/interviews.py', 'w', encoding='utf-8') as f:
    f.write(int_txt)
print('Updated frontend/iqui/views/interviews.py')
