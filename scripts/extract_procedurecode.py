import requests
import json
import csv

proc_count = {"SqlCommand": "SELECT COUNT(*) AS Count FROM procedurecode"}

response = requests.put('https://api.opendental.com/api/v1/queries/ShortQuery',
        headers={'Authorization': 'ODFHIR 8VHR0kOxeq13SXEX/pzH52RZEGousxzut'}, json=proc_count)
json_object = json.loads(response.content)
count_rows = json_object[0]['Count']
print(f"Total = {count_rows}")
with open("procedure_code1.csv", "w", newline='') as f:
    csvwriter = csv.writer(f)
    csvwriter.writerow(["CodeNum", "ProcCode", "Descript", "AbbrDesc", "ProcCat", "Category Name"])
    for i in range(7, int((count_rows+99)/100)):
        print(f"Fetch {i*100} - {i*100+100}")
        query = f"SELECT * FROM procedurecode WHERE CodeNum >= {i*100} AND CodeNum < {i*100+100} "
        newquery='''{"SqlCommand": "''' + query + '''" }'''
        response = requests.put('https://api.opendental.com/api/v1/queries/ShortQuery',
                headers={'Authorization': 'ODFHIR 8VHR0kOxeq13SXEX/pzH52RZEGousxzut'}, json=json.loads(newquery))
        json_object = json.loads(response.content)
        for proc in json_object:
            query_cate = f"SELECT ItemName from definition WHERE DefNum = {proc['ProcCat']}"
            newquery_cate='''{"SqlCommand": "''' + query_cate + '''" }'''
            response = requests.put('https://api.opendental.com/api/v1/queries/ShortQuery',
                headers={'Authorization': 'ODFHIR 8VHR0kOxeq13SXEX/pzH52RZEGousxzut'}, json=json.loads(newquery_cate))
            json_itemname = json.loads(response.content)
            csvwriter.writerow([proc['CodeNum'], proc['ProcCode'], proc['Descript'], proc['AbbrDesc'], proc['ProcCat'], json_itemname[0]['ItemName']])
