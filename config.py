# -*- coding: utf-8 -*-

"""
场地ID配置文件
"""

# -----------------用户配置-----------------
# 请在这里更新您的 Token 和 Member ID
TOKEN = "5ff0eaa0-a09c-4fa0-9fda-ede3dc32a0c8"
MEMBER_ID = "1697570245594587136"

# -----------------犀浦校区-----------------
# 犀浦校区羽毛球馆ID
XIPU_FIELDID = '1462412671863504896'

# 犀浦校区羽毛球场ID
XIPU_PLACEID = {
    1: '1560140784755286016',  # 一号
    2: '1560140847158140928',  # 二号
    3: '1560140914774515712',  # 三号
    4: '1560140972051521536',  # 四号
    5: '1560141308740886528',  # 五号
    6: '1560141364299046912',  # 六号
    7: '1581847774245806080',  # 七号
    8: '1581847774254194688',  # 八号
    9: '1581847774275166208',  # 九号
}

# -----------------九里校区-----------------
# 九里校区羽毛球馆ID
JIULI_FIELDID = '1462312540799516672'

# 九里校区羽毛球场ID
JIULI_PLACEID = {
    1: '1519942071047168000',  # 一号
    2: '1519942071089111040',  # 二号
    3: '1519942071110082560',  # 三号
    4: '1519942071131054080',  # 四号
    5: '1519942071152025600',  # 五号
    6: '1519942071172997120',  # 六号
}


# -----------------预约设置-----------------

# 选择校区: 'xipu' 或 'jiuli'
# SELECTED_CAMPUS = 'xipu'
SELECTED_CAMPUS = 'xipu'

# 选择场地编号:
# 犀浦: 1-9
# 九里: 1-6
SELECTED_COURT_NUMBER = 6


def get_selected_ids():
    """
    根据选择的校区和场地编号，返回对应的fieldId和placeId
    """
    if SELECTED_CAMPUS == 'xipu':
        field_id = XIPU_FIELDID
        place_id = XIPU_PLACEID.get(SELECTED_COURT_NUMBER)
    elif SELECTED_CAMPUS == 'jiuli':
        field_id = JIULI_FIELDID
        place_id = JIULI_PLACEID.get(SELECTED_COURT_NUMBER)
    else:
        raise ValueError("无效的校区选择，请选择 'xipu' 或 'jiuli'")

    if not place_id:
        raise ValueError(f"在 {SELECTED_CAMPUS} 校区未找到编号为 {SELECTED_COURT_NUMBER} 的场地")

    return field_id, place_id

