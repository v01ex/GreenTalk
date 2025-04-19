import re

# Read the file
with open('server_flask.py', 'r', encoding='utf-8') as file:
    content = file.read()

# Update index route
pattern = r'@app\.route\(\'/\'\)\s*def index\(\):\s*if \'username\' in session:\s*# Если пользователь авторизован, показываем главную страницу\s*return render_template\(\'home\.html\'\)'
replacement = '@app.route(\'/\')\ndef index():\n    if \'username\' in session:\n        # Если пользователь авторизован, перенаправляем в модерн чат\n        return redirect(url_for(\'modern_chat\'))'
content = re.sub(pattern, replacement, content)

# Update login redirect
pattern = r'session\[\'username\'\] = username\s*return redirect\(url_for\(\'private_chats\'\)\)'
replacement = 'session[\'username\'] = username\n            return redirect(url_for(\'modern_chat\'))'
content = re.sub(pattern, replacement, content)

# Update register redirect
pattern = r'session\[\'username\'\] = username\s*flash\(f\'Регистрация прошла успешно! Добро пожаловать, {name}\', \'success\'\)\s*return redirect\(url_for\(\'private_chats\'\)\)'
replacement = 'session[\'username\'] = username\n            flash(f\'Регистрация прошла успешно! Добро пожаловать, {name}\', \'success\')\n            return redirect(url_for(\'modern_chat\'))'
content = re.sub(pattern, replacement, content)

# Update profile redirects
pattern = r'return redirect\(url_for\(\'private_chats\'\)\)'
replacement = 'return redirect(url_for(\'modern_chat\'))'
content = re.sub(pattern, replacement, content)

# Update private_chats route to redirect to modern_chat
pattern = r'@app\.route\(\'/private_chats\', endpoint=\'private_chats\'\)\s*def private_chats\(\):\s*if \'username\' not in session:\s*return redirect\(url_for\(\'login\'\)\)\s*return render_template\(\'private_chats\.html\', username=session\[\'username\'\]\)'
replacement = '@app.route(\'/private_chats\', endpoint=\'private_chats\')\ndef private_chats():\n    if \'username\' not in session:\n        return redirect(url_for(\'login\'))\n    # Redirect to modern chat\n    return redirect(url_for(\'modern_chat\'))'
content = re.sub(pattern, replacement, content)

# Update favorites route to redirect to modern_chat
pattern = r'@app\.route\(\'/favorites\'\)\s*def favorites\(\):\s*if \'username\' not in session:\s*return redirect\(url_for\(\'login\'\)\)\s*return render_template\(\'favorites\.html\', username=session\[\'username\'\]\)'
replacement = '@app.route(\'/favorites\')\ndef favorites():\n    if \'username\' not in session:\n        return redirect(url_for(\'login\'))\n    # Redirect to modern chat\n    return redirect(url_for(\'modern_chat\'))'
content = re.sub(pattern, replacement, content)

# Write the updated content back to the file
with open('server_flask.py', 'w', encoding='utf-8') as file:
    file.write(content)

print("Routes updated successfully!") 