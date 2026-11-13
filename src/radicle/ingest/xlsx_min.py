"""Minimal stdlib .xlsx reader (shared strings + sheets). Only what the AGC harvest file needs."""
import zipfile,re
def read_xlsx(path):
    z=zipfile.ZipFile(path)
    ss=[re.sub(r"<[^>]+>","",s) for s in re.findall(r"<si>(.*?)</si>",z.read("xl/sharedStrings.xml").decode(),flags=re.S)]
    names=re.findall(r'<sheet [^>]*name="([^"]+)"[^>]*r:id="([^"]+)"',z.read("xl/workbook.xml").decode())
    rels=dict(re.findall(r'<Relationship [^>]*Id="([^"]+)"[^>]*Target="([^"]+)"',z.read("xl/_rels/workbook.xml.rels").decode()))
    rels.update({a:b for b,a in re.findall(r'<Relationship [^>]*Target="([^"]+)"[^>]*Id="([^"]+)"',z.read("xl/_rels/workbook.xml.rels").decode())})
    out={}
    for n,rid in names:
        x=z.read("xl/"+rels[rid].lstrip("/").replace("xl/","")).decode(); rows=[]
        for r in re.findall(r"<row[^>]*>(.*?)</row>",x,flags=re.S):
            cells={}
            for a,body in re.findall(r"<c ([^>]*?)(?:/>|>(.*?)</c>)",r,flags=re.S):
                ref=re.search(r'r="([A-Z]+)\d+"',a).group(1); v=re.search(r"<v>(.*?)</v>",body or "")
                if v: cells[ref]=ss[int(v.group(1))] if 't="s"' in a else v.group(1)
            rows.append(cells)
        out[n.strip()]=rows
    return out
