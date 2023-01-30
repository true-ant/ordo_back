import csv

from services.opendental import OpenDentalClient

proc_count = {"SqlCommand": "SELECT COUNT(*) AS Count FROM procedurecode"}

od_client = OpenDentalClient("ODFHIR 8VHR0kOxeq13SXEX/pzH52RZEGousxzut")

json_object = od_client.query(proc_count)
count_rows = json_object[0]["Count"]
print(f"Total = {count_rows}")
with open("procedure_code1.csv", "w", newline="") as f:
    csvwriter = csv.writer(f)
    csvwriter.writerow(["CodeNum", "ProcCode", "Descript", "AbbrDesc", "ProcCat", "Category Name"])
    for i in range(7, int((count_rows + 99) / 100)):
        print(f"Fetch {i * 100} - {i * 100 + 100}")
        query = f"SELECT * FROM procedurecode WHERE CodeNum >= {i * 100} AND CodeNum < {i * 100 + 100} "
        json_object = od_client.query(query)
        for proc in json_object:
            query_cate = f"SELECT ItemName from definition WHERE DefNum = {proc['ProcCat']}"
            json_itemname = od_client.query(query_cate)
            csvwriter.writerow(
                [
                    proc["CodeNum"],
                    proc["ProcCode"],
                    proc["Descript"],
                    proc["AbbrDesc"],
                    proc["ProcCat"],
                    json_itemname[0]["ItemName"],
                ]
            )
