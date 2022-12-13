import requests
import json
import csv

proc_count = {"SqlCommand": "SELECT COUNT(*) AS Count FROM procedurecode"}

response = requests.put('https://api.opendental.com/api/v1/queries/ShortQuery',
        headers={'Authorization': 'ODFHIR 8VHR0kOxeq13SXEX/pzH52RZEGousxzut'}, json=proc_count)
json_object = json.loads(response.content)
count_rows = json_object[0]['Count']

with open("procedure_code.csv", "w", newline='') as f:
    csvwriter = csv.writer(f)
    csvwriter.writerow(["CodeNum", "ProcCode", "Descript", "AbbrDesc", "ProcCat"])
    for i in range(int((count_rows+99)/100)):
        query = f"SELECT * FROM procedurecode WHERE CodeNum >= {i*100} AND CodeNum < {i*100+100} "
        newquery='''{"SqlCommand": "''' + query + '''" }'''
        response = requests.put('https://api.opendental.com/api/v1/queries/ShortQuery',
                headers={'Authorization': 'ODFHIR 8VHR0kOxeq13SXEX/pzH52RZEGousxzut'}, json=json.loads(newquery))
        json_object = json.loads(response.content)
        for proc in json_object:
            csvwriter.writerow([proc['CodeNum'], proc['ProcCode'], proc['Descript'], proc['AbbrDesc'], proc['ProcCat']])