with open('server_flask.py', 'r', encoding='utf-8') as file:
    lines = file.readlines()

# Fix indentation error in handle_disconnect (around line 1697)
if len(lines) >= 1697:
    if lines[1696].strip() == "if 'username' in session:":
        lines[1696] = "        if 'username' in session:\n"

# Fix indentation error in handle_send_private_message (around line 1811)
if len(lines) >= 1811:
    if lines[1810].strip() == "conn = get_db_connection()":
        lines[1810] = "            conn = get_db_connection()\n"

if len(lines) >= 1821:
    if lines[1820].strip() == "conn.close()":
        lines[1820] = "            conn.close()\n"

with open('server_flask.py', 'w', encoding='utf-8') as file:
    file.writelines(lines)

print("Indentation errors fixed successfully!") 