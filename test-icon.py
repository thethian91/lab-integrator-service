# flake8: noqa

import socket

VT = b"\x0b"
FS = b"\x1c"
CR = b"\x0d"

hl7 = (
    # noqa:
    "MSH|^~\\&|Icon-3|NI30H24105|LIS Application|LIS|20250821100844||ORU^R01|638913677245350000|P|2.5||||||UNICODE UTF-8\r"
    "SFT|N|1.3.2596.0|Icon-3|1.3.2596.0|Product Version: 0.9 Software complete version: 1.3.2596.0(FE - 00 - 45)|20240124034738\r"
    "PID|678||^^|||||O||||||||||||||||||||||||||||\r"
    "OBR|||^^^563||||20250811064326|25||||3 Part Differential Hematology\r"
    "NTE|Comment1|||1^Name\r"
    "NTE|Comment2|||2^Age\r"
    "OBX|1|NM|0^RBC||6.24|10^6/µL|4.50-5.90||||F\r"
    "OBX|2|NM|1^HGB||186|g/L|135-175||||F\r"
    "OBX|3|NM|2^MCV||102.0|fL|80-100||||F\r"
    "OBX|4|NM|3^HCT||63.6|%|40-54||||F\r"
    "OBX|5|NM|4^MCH||30.10|pg|27-33||||F\r"
    "OBX|6|NM|5^MCHC||296|g/L|320-360||||F\r"
    "OBX|7|NM|6^RDWsd||51.2|fL|39-46||||F\r"
    "OBX|8|NM|7^RDWcv||17.5|%|11.5-14.5||||F\r"
    "OBX|9|NM|8^PLT||446|10^3/µL|150-400||||F\r"
    "OBX|10|NM|9^MPV||7.8|fL|7.5-11.5||||F\r"
    "OBX|11|NM|10^PCT||0.35|%|0.22-0.24||||F\r"
    "OBX|12|NM|11^PDWsd||9.9|fL|9.6-15.0||||F\r"
    "OBX|13|NM|12^PDWcv||51.1|%|40-60||||F\r"
    "OBX|14|NM|13^WBC||23.0|10^3/µL|4.0-11.0||||F\r"
    "OBX|15|NM|14^LYM||13.4|10^3/µL|1.0-4.0||||F\r"
    "OBX|16|NM|15^LYMP||58.2|%|20-40||||F\r"
    "OBX|17|NM|16^MID||3.7|10^3/µL|0.1-1.0||||F\r"
    "OBX|18|NM|17^MIDP||15.9|%|2-8||||F\r"
    "OBX|19|NM|18^GRA||6.0|10^3/µL|2.0-7.0||||F\r"
    "OBX|20|NM|19^GRAP||25.9|%|50-70||||F\r"
    "NTE|WD1||85|1^WBC Discriminator #1 (fL)\r"
    "NTE|WD2||143|2^WBC Discriminator #2 (fL)\r"
)

# Encapsular en MLLP
mllp_message = VT + hl7.encode("utf-8") + FS + CR

# Enviar por TCP
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect(("127.0.0.1", 5002))  # Cambia la IP si es necesario
    s.sendall(mllp_message)
    print("✅ Mensaje HL7 de ICON-3 enviado con MLLP")
