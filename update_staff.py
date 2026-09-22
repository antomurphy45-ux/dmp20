from pathlib import Path
p=Path('/mnt/data/phase16/app.py')
s=p.read_text()
# Add staff migrations after company logo migration
needle='    company_cols={r[1] for r in c.execute("PRAGMA table_info(companies)").fetchall()}\n'
insert='''    staff_cols={r[1] for r in c.execute("PRAGMA table_info(staff)").fetchall()}\n    for col, typ in [("labour_level","TEXT NOT NULL DEFAULT ''"),("badge_type","TEXT NOT NULL DEFAULT ''"),("source_group","TEXT NOT NULL DEFAULT ''"),("display_color","TEXT NOT NULL DEFAULT ''")]:\n        if col not in staff_cols: c.execute(f"ALTER TABLE staff ADD COLUMN {col} {typ}")\n'''
assert needle in s
s=s.replace(needle, insert+needle,1)
# Insert function before seed_dub_demo_data
needle='def seed_dub_demo_data(c):\n'
func=r'''def seed_image_staff(c):
    """Seed the staff register from the supplied labour-board screenshots.
    The screenshot legend defines the labour level colours. Badge markers are
    retained as metadata: * = Airport Badge, ** = AWS Badge, */** = both.
    No project dates or assignments are invented from the image.
    """
    company_id="C1"
    people=[
        ("IMG-COLM-KEIGHERY","Colm Keighery","Unspecified","","AWS Ballycoolin / AWS Tyrellstown","#ffffff"),
        ("IMG-JAMIE-MURRAY","Jamie Murray","Electrician","AWS Badge","AWS Ballycoolin / AWS Tyrellstown","#ff0000"),
        ("IMG-LORCAN-OTOOLE","Lorcan O'Toole","Electrician","AWS Badge","AWS Ballycoolin / AWS Tyrellstown","#ff0000"),
        ("IMG-SEAN-TIMLIN","Sean Timlin","2nd Year","AWS Badge","AWS Ballycoolin / AWS Tyrellstown","#00ff00"),
        ("IMG-CALUM-DALY","Calum Daly","2nd Year","Airport Badge + AWS Badge","AWS Ballycoolin / AWS Tyrellstown","#00ff00"),
        ("IMG-IAN-FOX","Ian Fox (T)","Site Management","AWS Badge","AWS Clon (E2882)","#ffbd0a"),
        ("IMG-JORDAN-LAWRENCE","Jordan Lawrence","Site Management","AWS Badge","AWS Clon (E2882)","#ffbd0a"),
        ("IMG-JAKE-SHERLOCK","Jake Sherlock","Site Management","AWS Badge","AWS Clon (E2882)","#ffbd0a"),
        ("IMG-MARK-GIBSON","Mark Gibson (T)","Charge Hand","AWS Badge","AWS Clon (E2882)","#5b8f3b"),
        ("IMG-CONOR-FITZPATRICK","Conor Fitzpatrick (T)","Charge Hand","AWS Badge","AWS Clon (E2882)","#5b8f3b"),
        ("IMG-PRATIK-KAMBLE","Pratik Kamble","Engineers","","AWS Clon (E2882)","#f6d1ab"),
        ("IMG-ROSS-DOUGLAS","Ross Douglas","Engineers","Airport Badge","AWS Clon (E2882)","#f6d1ab"),
        ("IMG-DEAN-SMITH","Dean Smith","Electrician","AWS Badge","AWS Clon (E2882)","#ff0000"),
        ("IMG-KEITH-MURRAY","Keith Murray","Electrician","AWS Badge","AWS Clon (E2882)","#ff0000"),
        ("IMG-CONOR-SNELL","Conor Snell","Electrician","Airport Badge + AWS Badge","AWS Clon (E2882)","#ff0000"),
        ("IMG-COLM-COX","Colm Cox","Electrician","Airport Badge + AWS Badge","AWS Clon (E2882)","#ff0000"),
        ("IMG-VIJAY-SUNDARAM","Vijay Sundaram (T)","Electrician","AWS Badge","AWS Clon (E2882)","#ff0000"),
        ("IMG-CHRISTIAN-WILLIAMS","Christian Williams","Electrician","Airport Badge + AWS Badge","AWS Clon (E2882)","#ff0000"),
        ("IMG-ADAM-POOLE","Adam Poole","Electrician","Airport Badge + AWS Badge","AWS Clon (E2882)","#ff0000"),
        ("IMG-DEAN-FLYNN","Dean Flynn","4th Year","AWS Badge","AWS Clon (E2882)","#ff00d8"),
        ("IMG-LUKE-OREILLY","Luke O'Reilly","3rd Year","AWS Badge","AWS Clon (E2882)","#ffff00"),
        ("IMG-DARRAGH-MURRAY","Darragh Murray","2nd Year","AWS Badge","AWS Clon (E2882)","#00ff00"),
        ("IMG-LEE-GALLAGHER","Lee Gallagher","2nd Year","AWS Badge","AWS Clon (E2882)","#00ff00"),
        ("IMG-SEAN-BOYLE","Sean Boyle","2nd Year","Airport Badge + AWS Badge","AWS Clon (E2882)","#00ff00"),
        ("IMG-DARIUS-DRAGUSIN","Darius Dragusin","2nd Year","AWS Badge","AWS Clon (E2882)","#00ff00"),
        ("IMG-STEPHEN-BLAKE","Stephen Blake","GO","AWS Badge","AWS Clon (E2882)","#c0c0c0"),
        ("IMG-ANTHONY-MURPHY","Anthony Murphy","Site Management","AWS Badge","DUB 10","#ffbd0a"),
        ("IMG-JOHN-SHELLEY","John Shelley (T)","Charge Hand","AWS Badge","DUB 10","#5b8f3b"),
        ("IMG-KEITH-MURPHY","Keith Murphy","Site Management","AWS Badge","Microsoft","#ffbd0a"),
        ("IMG-WILLIAM-OBRIEN","William O Brien","Site Management","AWS Badge","Vodafone (E2881)","#ffbd0a"),
    ]
    # Preserve historical rows/assignments but remove generic demo staff from the active register.
    c.execute("UPDATE staff SET active=0, updated_at=CURRENT_TIMESTAMP WHERE company_id=?",(company_id,))
    for ref,name,level,badge,group,color in people:
        row=c.execute("SELECT id FROM staff WHERE company_id=? AND staff_ref=?",(company_id,ref)).fetchone()
        # Position remains the established assignment vocabulary where possible; the screenshot level is stored separately.
        pos = {"Site Management":"Construction Manager","Charge Hand":"Charge Hand","Engineers":"Engineer","Electrician":"Electrician","4th Year":"4th Year","3rd Year":"3rd Year","2nd Year":"2nd Year","1st Year":"1st Year","GO":"GO","Unspecified":"Unspecified"}[level]
        if row:
            sid=row[0]
            c.execute("UPDATE staff SET name=?,position=?,active=1,labour_level=?,badge_type=?,source_group=?,display_color=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(name,pos,level,badge,group,color,sid))
        else:
            sid="ST-"+ref
            c.execute("INSERT OR IGNORE INTO staff(id,company_id,staff_ref,name,position,active,labour_level,badge_type,source_group,display_color) VALUES(?,?,?,?,?,?,?,?,?,?)",(sid,company_id,ref,name,pos,1,level,badge,group,color))
    # Repair any older rows that pre-date the new columns.
    c.execute("UPDATE staff SET labour_level=position WHERE company_id=? AND (labour_level IS NULL OR labour_level='')",(company_id,))
    c.commit()

'''
assert needle in s
s=s.replace(needle,func+needle,1)
# Call after dub84 seed in both seed paths; easiest replace occurrences
s=s.replace('        seed_dub84_from_source(c)\n        c.commit()', '        seed_dub84_from_source(c)\n        seed_image_staff(c)\n        c.commit()', 1)
s=s.replace('    seed_dub84_from_source(c)\n    repair_demo_project_access(c)', '    seed_dub84_from_source(c)\n    seed_image_staff(c)\n    repair_demo_project_access(c)', 1)
p.write_text(s)
