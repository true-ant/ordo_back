SET @FromDate='{day_from}',
@ToDate='{day_to}';
SELECT procs.ProcCode,COUNT(*) As Count,FORMAT(ROUND(AVG(procs.fee),2),2) AvgFee,SUM(procs.fee) AS TotFee
    FROM ( SELECT procedurelog.ProcFee*(procedurelog.UnitQty+procedurelog.BaseUnits) -COALESCE(SUM(claimproc.WriteOff),0) fee, procedurecode.ProcCode,procedurecode.AbbrDesc,procedurecode.Descript, definition.ItemName, definition.ItemOrder FROM procedurelog INNER JOIN procedurecode ON procedurelog.CodeNum=procedurecode.CodeNum INNER JOIN definition ON definition.DefNum=procedurecode.ProcCat LEFT JOIN claimproc ON claimproc.ProcNum=procedurelog.ProcNum AND claimproc.Status=7 WHERE procedurelog.ProcStatus=2 AND procedurelog.ClinicNum IN (0,2,1,3,6,7,5) AND procedurelog.ProcDate >= @FromDate AND procedurelog.ProcDate <= @ToDate GROUP BY procedurelog.ProcNum ) procs GROUP BY procs.ProcCode ORDER BY procs.ItemOrder,procs.ProcCode