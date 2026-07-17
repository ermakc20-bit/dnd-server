@app.post("/api/table/delete")
async def delete_table(data: dict):
    session = Session()
    try:
        table = session.query(GameTable).filter_by(id=data['table_id']).first()
        if not table:
            return {"success": False, "message": "Стол не найден"}
        table.is_active = False
        session.commit()
        return {"success": True, "message": "Стол удалён"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()
