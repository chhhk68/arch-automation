import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import math

api_key = "481D8237-0003-38A2-945A-487993C360EA"
lon, lat = 127.03651446855193, 37.50002857167398

def wgs84_to_tm(lon_deg, lat_deg):
    a=6378137.0; f=1/298.257222101; b=a*(1-f); e2=1-(b/a)**2
    lon0,lat0=math.radians(127.5),math.radians(38.0)
    FE,FN,k0=1000000.0,2000000.0,1.0
    p,l=math.radians(lat_deg),math.radians(lon_deg)
    N=a/math.sqrt(1-e2*math.sin(p)**2)
    T=math.tan(p)**2; C=e2/(1-e2)*math.cos(p)**2; A=math.cos(p)*(l-lon0)
    M=a*((1-e2/4-3*e2**2/64)*p-(3*e2/8+3*e2**2/32)*math.sin(2*p)+(15*e2**2/256)*math.sin(4*p))
    M0=a*((1-e2/4-3*e2**2/64)*lat0-(3*e2/8+3*e2**2/32)*math.sin(2*lat0)+(15*e2**2/256)*math.sin(4*lat0))
    x=FE+k0*N*(A+(1-T+C)*A**3/6+(5-18*T+T**2+72*C)*A**5/120)
    y=FN+k0*(M-M0+N*math.tan(p)*(A**2/2+(5-T+9*C+4*C**2)*A**4/24+(61-58*T+T**2+600*C)*A**6/720))
    return x, y

tx, ty = wgs84_to_tm(lon, lat)
d = 2000  # 2km 범위

# lt_c_lhzone 도 포함해서 모든 가능한 레이어 시도
layers = ["lt_c_lhzone", "lt_c_uq111","lt_c_uq112","lt_c_uq121","lt_c_uq122",
          "lt_c_uq123","lt_c_uq124","lt_c_uq125","lt_c_uq126","lt_c_uq128",
          "lt_c_uq129","lt_c_uq130","lt_c_uq141","lt_c_uq162"]

bbox_tm = f"{tx-d},{ty-d},{tx+d},{ty+d}"

for layer in layers:
    url = "https://api.vworld.kr/req/wfs?" + urllib.parse.urlencode({
        "SERVICE":"WFS","VERSION":"1.1.0","REQUEST":"GetFeature",
        "TYPENAME":layer,"KEY":api_key,
        "MAXFEATURES":"1","BBOX":bbox_tm,"SRSNAME":"EPSG:5179",
    })
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        body = r.read().decode("utf-8")
    root = ET.fromstring(body)
    members = list(root.iter("{http://www.opengis.net/wfs}member"))
    n = len(members)
    print(f"{layer}: {n}건" + (" <--" if n else ""))
