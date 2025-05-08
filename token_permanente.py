import requests


APP_ID = ''
APP_SECRET = ''
SHORT_LIVED_TOKEN = ''

url = f"https://graph.facebook.com/v19.0/oauth/access_token?grant_type=fb_exchange_token&client_id={APP_ID}&client_secret={APP_SECRET}&fb_exchange_token={SHORT_LIVED_TOKEN}"


response = requests.get(url)

if response.status_code == 200:
    data = response.json()
    long_lived_token = data['access_token']
    expires_in = data.get('expires_in', 'unknown')
    print(f"Token de larga duración obtenido:\n{long_lived_token}")
    print(f"Este token expira en aproximadamente {expires_in} segundos (~{expires_in/3600/24:.1f} días).")

    #Guardar en un archivo de texto
    with open('long_lived_token.txt', 'w') as f:
        f.write(long_lived_token)
    print("Token guardado en 'long_lived_token.txt'")
else:
    print(f"Error al obtener token largo: {response.text}")
