import requests
import sys
import json
import time
import datetime

def test_edit_profile():
    with requests.Session() as session:
        # First create a test user
        print("Creating test user...")
        create_user_url = "http://127.0.0.1:5000/api/debug/create_test_user"
        user_response = session.get(create_user_url)
        
        if user_response.status_code != 200:
            print(f"Failed to create test user: {user_response.status_code}")
            print(user_response.text)
            return
        
        user_data = user_response.json()
        print(f"Test user response: {json.dumps(user_data, indent=2)}")
        
        # Extract username and password
        username = user_data["user"]["username"]
        password = user_data["user"]["password"]
        
        # Login with the test user
        login_url = "http://127.0.0.1:5000/login"
        login_data = {
            "username": username,
            "password": password
        }
        
        print(f"\nAttempting to login with username={username}, password={password}...")
        login_response = session.post(login_url, data=login_data)
        
        print(f"Login response URL: {login_response.url}")
        print(f"Login response status code: {login_response.status_code}")
        
        if "private_chats" in login_response.url:
            print("Login successful!")
            
            # Try debug route first
            print("\nAttempting to access debug_profile endpoint...")
            debug_url = "http://127.0.0.1:5000/debug_profile"
            debug_response = session.get(debug_url)
            
            print(f"Debug status code: {debug_response.status_code}")
            if debug_response.status_code == 200:
                print("Successfully accessed debug_profile endpoint!")
                debug_data = debug_response.json()
                print("\nUser data from debug endpoint:")
                print(json.dumps(debug_data, indent=2))
            else:
                print("Failed to access debug_profile endpoint")
                print(debug_response.text)
            
            # Wait a moment
            time.sleep(1)
            
            # Now try to access the edit_profile page
            print("\nAttempting to access edit_profile page...")
            edit_profile_url = "http://127.0.0.1:5000/edit_profile"
            response = session.get(edit_profile_url)
            
            print(f"Status code: {response.status_code}")
            if response.status_code == 200:
                print("Successfully accessed edit_profile page!")
                # Save the response HTML to a timestamped file for inspection
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"edit_profile_response_{username}_{timestamp}.html"
                with open(output_filename, "w", encoding="utf-8") as f:
                    f.write(response.text)
                print(f"Response saved to {output_filename}")
            else:
                print("Failed to access edit_profile page")
                print(response.text)
        else:
            print("Login failed. Check username and password.")
            page_content = login_response.text
            if "Неверное имя пользователя или пароль" in page_content:
                print("Error message in response: 'Неверное имя пользователя или пароль'")
            print("First 200 characters of response content:")
            print(page_content[:200])

if __name__ == "__main__":
    test_edit_profile() 