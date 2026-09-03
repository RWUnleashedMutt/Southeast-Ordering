SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

SHEET_IDS = {
    'HQ Min/Max Orders': '1W-AGqIXwcqL7clDHad43hFmpPrrXzNUDYC4-dVGpngo',
    '2 Hounds': '1zT3zsX2eFPLRk430Q-c5QmWsXJHDSej97EI_ivl-q0A',
    'Adored Beast': '1HwOxpAzI_HlntVVfOqxBVAWDy7cznPxxhUqOR5cy6ng',
    'Ark Naturals': '1hgs38gm96v_ZansdVJTdr4JEsK-6TTarlbuBIr2V9C0',
    'Aroma Paws': '1fTvxu-y3rVpvxkt8elR1bZMECReblLE0zmYQDr1ePPg',
    'Big Spoon Roasters': '1VlH5VEWqexB4mxd4PsQx9gg3uu8tqyBi_QC01EiDEkQ',
    'Bradley Caldwell': '1eqENDXTdDJVKdos-VUXYNYMNM806rNcDrv63Q654nyc',
    'Brilliant Salmon Oil': '1ZJg6pPEf502MZVGCvuQcxDFHXMhWep0xdyA4xlj92aw',
    'Butchers Block': '1nDtvvDVu9tAzR2iDB4uMpUG3rcN3Fm_v09WJw3jvbJI',
    'Canine Caviar': '1TJXe9V_aF1A1wm_O9XK_iWJNU119iH3ZBBorUlX_0ss',
    "Coastal": "1XZ_X_5nPcGON4wmwFzBZG6cVrOzlXncKhoSq2JQi3yM",
    'Colorado Pet Treats': '1U4nQGJvgyPWLST96Y6a4yrgJ2jGGicS6p4f7jesL8p8',
    'Comfy Cone': '15SuKA1HiSOZDs78x1ZgQOG0cUXnZ-kBJyKsUG59btQY',
    'Dexy Paws': '1fux791xEUU9shk2kyyFK6B-f6sjJlx3zser-jq9oHYU',
    'Dezi Roo': '1JwTm3gHTLXlGUlOTGQdteNMSIZnQMt6Z2uqE6R4_o_A',
    'Evangers': '1Lg9-ar14KHJDgWjFGqFbhuh-1-OM_BpA3ABIaoWe_gE',
    'Flexi': '1F8vF7XQlzJArpTTJaNq2rcYx8n-5hMwRzvwpjQVVlB0',
    'Fluff & Tuff': '1nGWM9Lt34e3vpqaETjPeMVsCTKVC9kIEQ3VVx1mEUqY',
    'From The Field': '1wfs8bWVlUwJ1L6O518QkA8uheX0agIeSubnAO0-XYCo',
    'Front Porch Pets': '1CyW8rNNWzmYH9iqVRgN5iTWCiqgd-cJnrAJGktGS2a0',
    'Glacier Peak': '1iLFcfirV-2knXYGDqEE4721DtaRP_KFDgmtO-WsChMo',
    'Go Cat': '1FO0eFavBINXOgHXTiJvhEf9lvYdHQsQEgusJ62RLGrc',
    'Great Lakes': '1ajpaKEq8XR-M_Wu9m_VOhMfmHkjjmOXYfGWENg8j02s',
    'Homeopet': '1O35i1E_1lWxOkTJTvaURW2_qwlVO2YGaoBRfFvcstjE',
    'InClover': '1GJX-rqphRYAHM50HKrXhE3qG3ZUeB9kP0njwcuM56co',
    'Kennel Master': '1YgbCH_UxFZYAKnyJRki1ReNIdgqyUHtPS8gztUbpJaQ',
    'Mountain Dog': '14lPZsNmNS42gnXIh5Kh9nPRVCAep59hwj1Awj4H8v3Q',
    'Multi Pet': '1KjTgp4NCL5EXM7kKUrI-FIfVzvh9UYXBgz3o24RkeXU',
    'Myos': '13wEZ1Y9REyUJwjSRmXT46dZoW9DDUXdNrsw5JFgghHA',
    'Nite Ize': '1fOfm-gDo5l4-ddrBtcVbnZkTox-zRtEdkgKyoJMl2YY',
    'Nordic Naturals': '1QvApqLGh0uFcRbbNLkpxcyqMdihM_zrc2cvvJEJ9YEg',
    'PAW': '1pWnAVNS2oRb38Dv1oXR2mwhdQbVCSG2tnUVCM-5SrTo',
    'Petmate': '1uOuHEjbHli6LVMsgDJbrfiuV1B9_QftMMeiqPH_C5bM',
    'Petsafe': '1ZTxuc7mazD40A3q76-G9EDPmI6O5nFLvtRlloo5eWQs',
    'Phillips': '1AyaU_YubXM5Qx88Deo7Nj3OFUBTeIzx4VUXawe_YeWI',
    'Playology': '1crFl1pFzMluFAcUTuMcrTaAJGETtua3iU8L8HIELny8',
    'Plush': '1Rz6SaJjBGvCIhcOEXa_UesSxJyP59BTKn2SwbmqRxd4',
    'Polka Dog': '1JUFN_ErS6FXUKD9gv_RzccxJplwpEDiaX3Am4LW0shw',
    'QT Dog': '1__-S-g-FdiuwKFyTZYq7fCJTwN3irMqHfvF99hrMhLY',
    'Ruff Dawg': '1HpXiQn4RsNbdG0DtCKu9xjQ_W9Q9qa0DrDaFZiTroIw',
    'Ruffwear': '1MiiuAI7pqjKwhwi_MsiINBUOpvc_uq7OrGJ8BSln2xg',
    'SE': '1O6HWGeLgtdScnJ0_pQc8asaSj3-L4pP9vjCvvXa26vQ',
    'Trueblue': '1vvMahz0JVn-_mO_Dry5amhebKbc_T_hAzVJYarP8o-U',
    'Tuesdays Natural Dog': '1f_iWF48FflsFBlVkR3P5Sk49Q87Q8Fpl8tklKYKsHtk',
    'Unique': '1Cf40Nm57h2gm_le_0gOV-jHfSpHjJHb6F8-0wP1cA0s',
    'WPO': '1ySBJWhHh9_F_kAD3tvNZNA9ZuPLOAx3xfX_MwqOYCOA',
    'Wild Meadow Farms': '1NOkBS71fYQSOtIs_cwWMGmn0WDJK8YfO51GVyVxaMEg',
    'Winnie Lou': '1sFhwEVHFhAZI9mgVLCy1EFUR3He76ZrJFEJP1BiH2gQ',
    'Yeowww': '1hjWpchgn0wVeZZ4Pp_Juecy6bQaVW2C_cmZrKcNKziU',
    'Zenta': '1x1mH8ldOwNLXOLtf8RXhSHQliOUO9mNZmHtliTpPWKw'
}

store_map = {
    'Current Quantity City Market: DTR': 'CM',
    'Current Quantity Crabtree Valley Mall': 'CVM',
    'Current Quantity Crescent Commons': 'CC',
    'Current Quantity Downtown Durham': 'DTD',
    'Current Quantity Front Street': 'MF',
    'Current Quantity Lake Boone': 'LB',
    'Current Quantity Landfall Shopping Center': 'LF',
    'Current Quantity Parkway Plaza': 'PP',
    'Current Quantity Southport - Tidewater': 'SP',
    'Current Quantity Stonehenge Market': 'SH',
    'Current Quantity The Streets at Southpoint': 'SS'
}

inv_store_map = {v: k for k, v in store_map.items()}
priority_stores = ['CC', 'CM', 'CVM', 'LB', 'SH']
