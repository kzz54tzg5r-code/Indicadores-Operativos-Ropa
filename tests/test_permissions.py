import pandas as pd, pytest
from core.permissions import AccessContext, apply_scope, protect_owner
def test_store_scope_blocks_other_store():
 d=pd.DataFrame({"Tienda":["A","B"],"Piezas":[1,2]}); o=apply_scope(d,AccessContext("TIENDA","STORE",stores=("A",))); assert o["Tienda"].tolist()==["A"]
def test_region_scope():
 d=pd.DataFrame({"Región":["N","S"],"Tienda":["A","B"]}); assert len(apply_scope(d,AccessContext("REGIONAL","REGION",regions=("N",))))==1
def test_owner_protected():
 with pytest.raises(PermissionError): protect_owner(AccessContext("ADMIN"),"OWNER","delete")
