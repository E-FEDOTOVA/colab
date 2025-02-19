# -*- coding: utf-8 -*-
"""CallSync.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1ByEGkel0CHC-7QVuxZxzT98aEKKoSX-h

## Installing Required Libraries
This cell installs the necessary Python libraries for the script to work, including:
- `python-dotenv`: For managing environment variables.
- `google-api-python-client`, `google-auth-httplib2`, and `google-auth-oauthlib`: For interacting with Google APIs.
- `gspread` and `gspread_dataframe`: For working with Google Sheets.
- `pandas`: For data processing.

🔹 **Run this cell once before executing the rest of the script.**
"""

!pip install python-dotenv
!pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
!pip install --upgrade gspread pandas gspread_dataframe

"""## Importing Required Libraries & Authenticating Google Services
This cell:
- Imports necessary Python libraries.
- Authenticates Google Drive and Google Sheets access.
- Defines important constants like `API_KEY` and `drive_folder_name`.

🔹 **You need to grant Google Drive access when prompted.**

"""

import os
import requests
import sys
import pandas as pd
import gspread
from gspread_dataframe import set_with_dataframe
from google.colab import auth
from google.auth import default
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from google.colab import userdata

API_KEY = userdata.get('RINGOVER_API_KEY')

# ✅ Start runtime logging
py_start = datetime.now()

API_URL = "https://public-api-us.ringover.com/v2/calls"

# ✅ Authenticate Google Drive
auth.authenticate_user()
creds, _ = default()
gc = gspread.authorize(creds)
drive_service = build('drive', 'v3', credentials=creds)

# Get yesterday's date
target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


# ✅ Define Google Drive folder name
drive_folder_name = "RingoverLogs"
sheet_name = f"Detailed_Summary_{target_date}"

# ✅ Get Google Drive Folder ID
def get_drive_folder_id(folder_name):
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder'"
    response = drive_service.files().list(q=query, spaces='drive').execute()
    folders = response.get('files', [])

    if folders:
        return folders[0]['id']
    else:
        raise ValueError(f"❌ Folder '{folder_name}' not found in Google Drive. Please create it manually.")

try:
    folder_id = get_drive_folder_id(drive_folder_name)
except ValueError as e:
    print(e)
    folder_id = None

# Generate per‑call summary in JSON and CSV (using a simple summary)
def convert_utc_to_et(utc_time_str):
    if not utc_time_str or utc_time_str == "Unknown":
        return "Unknown"

    try:
        utc_time = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        utc_time = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%SZ")

    et_time = utc_time - timedelta(hours=5)  # Convert to ET (UTC-5)
    return et_time.strftime("%Y-%m-%d %H:%M:%S")


def fetch_calls_for_hour(hour):
    """Fetch call logs for a specific UTC hour adjusted from Eastern Time."""
    utc_hour = (hour + ET_TO_UTC_OFFSET) % 24  # Convert local hour to UTC hour
    start_time = f"{target_date}T{utc_hour:02d}:00:00.53Z"
    end_time = f"{target_date}T{utc_hour:02d}:59:59.53Z"

    params = {
        "start_date": start_time,
        "end_date": end_time,
        "direction": "out",
        "type": "PHONE",
        "filter": "all",
        "limit_count": 0,
        "limit_offset": 0,
        "ascending_order": True
    }

    headers = {
        "Authorization": API_KEY.strip(),
        "Content-Type": "application/json"
    }

    all_calls = []
    while True:
        try:
            response = requests.get(API_URL, headers=headers, params=params)

            if response.status_code == 200:
                data = response.json()
                call_logs = data.get("call_list", [])

                if not call_logs:
                    break  # No more calls to fetch

                all_calls.extend(call_logs)
                params["limit_offset"] += len(call_logs)  # Move to the next batch
            elif response.status_code == 204:
                break  # No content available for this hour
            else:
                print(f"\n❌ HTTP Error {response.status_code}: {response.text}")
                break
        except requests.exceptions.RequestException as error:
            print(f"\n❌ Error fetching call logs: {error}")
            break
        except KeyboardInterrupt:
            print("\n⏹️ Process interrupted! Saving partial results...")
            break

    sys.stdout.write(f"\r🕒 ET Hour {hour}: UTC Hour {utc_hour}: Total calls recorded: {len(all_calls)}\n")
    return all_calls

# Adjust for Eastern Time (EST: UTC-5)
ET_TO_UTC_OFFSET = 5  # ET is UTC-5 in February

# ✅ Fetch call logs hour by hour (ET hours 00-23 adjusted to UTC)
all_call_logs = []
for hour in range(24):  # Loop over Eastern Time hours
    all_call_logs.extend(fetch_calls_for_hour(hour))

print(f"\n✅ Total calls recorded: {len(all_call_logs)}")

# Save to JSON Function
def save_to_json(data, filename):
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)
    print(f"✅ Data saved to '{filename}'.")

# Save to CSV Function
def save_to_csv(data, filename, fieldnames):
    if not data:
        print("⚠️ No data to save.")
        return

    with open(filename, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    print(f"✅ Data saved to '{filename}'.")


# ✅ Check if a file exists and delete it
def delete_existing_file(file_name, folder_id):
    query = f"name = '{file_name}' and '{folder_id}' in parents"
    response = drive_service.files().list(q=query, spaces='drive').execute()
    files = response.get('files', [])

    for file in files:
        file_id = file['id']
        drive_service.files().delete(fileId=file_id).execute()
        print(f"🗑️ Deleted existing file: {file_name}")

# ✅ Apply Formatting to Google Sheet
def apply_sheet_formatting(spreadsheet_id):
    sheets_service = build('sheets', 'v4', credentials=creds)

    requests = [
        # ✅ Format Header Row (Bold, Background Color, Centered, Wrapped)
        {
            "repeatCell": {
                "range": {
                    "sheetId": 0,
                    "startRowIndex": 0,
                    "endRowIndex": 1  # Header row only
                },
                "cell": {
                    "userEnteredFormat": {
                        "wrapStrategy": "WRAP"
                    }
                },
                "fields": "userEnteredFormat(wrapStrategy)"
            }
        },
        # ✅ Wrap Text for Columns G (Index 6) and I (Index 8)
        {
            "repeatCell": {
                "range": {
                    "sheetId": 0,
                    "startColumnIndex": 6,  # Column G
                    "endColumnIndex": 7
                },
                "cell": {
                    "userEnteredFormat": {
                        "wrapStrategy": "WRAP"
                    }
                },
                "fields": "userEnteredFormat.wrapStrategy"
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": 0,
                    "startColumnIndex": 8,  # Column I
                    "endColumnIndex": 9
                },
                "cell": {
                    "userEnteredFormat": {
                        "wrapStrategy": "WRAP"
                    }
                },
                "fields": "userEnteredFormat.wrapStrategy"
            }
        },
         # ✅ Format Column E (First Call) and Column F (Last Call Complete) as Time (HH:MM AM/PM)
        {
            "repeatCell": {
                "range": {
                    "sheetId": 0,
                    "startColumnIndex": 4,  # Column E
                    "endColumnIndex": 6   # Column F
                },
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {
                            "type": "TIME",
                            "pattern": "hh:mm AM/PM"
                        }
                    }
                },
                "fields": "userEnteredFormat.numberFormat"
            }
        }
    ]

    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests}
    ).execute()

    print("✅ Formatting applied to Google Sheet!")
# ✅ Generate and save reports
def generate_detailed_summary(call_logs, sheet_name):
    user_calls = {}
    for call in call_logs:
        user = call.get("user")
        if not user:
            continue
        user_id = user.get("user_id")
        if user_id is None:
            continue
        user_calls.setdefault(user_id, []).append(call)

    summary_rows = []
    for user_id, calls in user_calls.items():
        first_user = calls[0].get("user", {})
        first_name = first_user.get("firstname", "Unknown")
        last_name = first_user.get("lastname", "Unknown")
        total_calls = len(calls)
        total_duration_sec = sum((call.get("total_duration") or 0) for call in calls)
        total_incall_sec = sum((call.get("incall_duration") or 0) for call in calls)
        total_incall_avg = round(total_incall_sec / total_calls, 2) if total_calls > 0 else 0

        # ✅ Count calls under 0.2 minutes (12 seconds)
        short_calls = sum(1 for call in calls if (call.get("total_duration") or 0) < 12)
        short_calls_percentage = round((short_calls / total_calls * 100), 2) if total_calls > 0 else 0

        # ✅ Extract first and last call times
        sorted_calls = sorted(calls, key=lambda x: x.get("start_time", "Unknown"))
        first_call_time = convert_utc_to_et(sorted_calls[0].get("start_time", "Unknown"))
        last_call_complete_time = convert_utc_to_et(sorted_calls[-1].get("end_time", "Unknown"))

        try:
            first_call_time = datetime.strptime(first_call_time, "%Y-%m-%d %H:%M:%S").strftime("%I:%M:%S %p")
            last_call_complete_time = datetime.strptime(last_call_complete_time, "%Y-%m-%d %H:%M:%S").strftime("%I:%M:%S %p")
        except:
            first_call_time = "N/A"
            last_call_complete_time = "N/A"

        # ✅ Identify call gaps
        gaps_15_30 = []
        gaps_30_plus = []
        for i in range(1, len(sorted_calls)):
            prev_end = convert_utc_to_et(sorted_calls[i-1].get("end_time", "Unknown"))
            curr_start = convert_utc_to_et(sorted_calls[i].get("start_time", "Unknown"))

            try:
                prev_end_time = datetime.strptime(prev_end, "%Y-%m-%d %H:%M:%S")
                curr_start_time = datetime.strptime(curr_start, "%Y-%m-%d %H:%M:%S")
                gap_minutes = (curr_start_time - prev_end_time).total_seconds() / 60

                if 15 <= gap_minutes < 30:
                    gaps_15_30.append(f"{prev_end_time.strftime('%I:%M %p')} - {curr_start_time.strftime('%I:%M %p')}")
                elif gap_minutes >= 30:
                    gaps_30_plus.append(f"{prev_end_time.strftime('%I:%M %p')} - {curr_start_time.strftime('%I:%M %p')}")
            except:
                continue

        summary_rows.append({
            "First Name": first_name,
            "Last Name": last_name,
            "% Calls <0.2 min": short_calls_percentage,
            "Total Calls": total_calls,
            "First Call": first_call_time,
            "Last Call Complete": last_call_complete_time,
            "Total Duration": total_duration_sec,
            "Total In Call": total_incall_sec,
            "Total In Call Average": total_incall_avg,
            "Number of Gaps (15-30 min)": len(gaps_15_30),
            "Gaps 15-30 min": "; ".join(gaps_15_30),
            "Number of Gaps (30+ min)": len(gaps_30_plus),
            "Gaps 30+ min": "; ".join(gaps_30_plus)
        })

    # ✅ Ensure correct column order
    column_order = [
        "First Name", "Last Name", "% Calls <0.2 min", "Total Calls",
        "First Call", "Last Call Complete", "Total Duration",
        "Total In Call", "Total In Call Average", "Number of Gaps (15-30 min)",
        "Gaps 15-30 min", "Number of Gaps (30+ min)", "Gaps 30+ min"
    ]

    df = pd.DataFrame(summary_rows, columns=column_order)

    # ✅ Delete old file if it exists
    if folder_id:
        delete_existing_file(sheet_name, folder_id)

    # ✅ Create new Google Sheet
    spreadsheet = gc.create(sheet_name)

    if folder_id:
        # ✅ Move new file to 'RingoverLogs' folder
        file_id = spreadsheet.id
        drive_service.files().update(fileId=file_id, addParents=folder_id, removeParents="root").execute()

    worksheet = spreadsheet.get_worksheet(0)
    set_with_dataframe(worksheet, df)  # Upload DataFrame to Google Sheet

    # ✅ Apply formatting
    apply_sheet_formatting(spreadsheet.id)
    os.environ["SPREADSHEET_URL"] = spreadsheet.url
    print(f"\n✅ Google Sheet saved in RingoverLogs: {spreadsheet.url}")


# ✅ Run the function
generate_detailed_summary(all_call_logs, sheet_name)

# ✅ End runtime logging
py_end = datetime.now()
processing_time = py_end - py_start
print(f"\n✅ Processing completed in: {processing_time}")

!pip install openai

"""## Fetching & Processing Data from Google Sheets
This cell:
- Loads data from Google Sheets.
- Processes and cleans the call data.
- Excludes specific individuals from the report.
- Identifies top performers and underperformers.

🔹 **Ensure that the correct Google Sheets document is accessible before proceeding.**

"""

import pandas as pd
from datetime import datetime
import openai
import os

# ✅ Set OpenAI API Key
api_key= userdata.get('OPENAI_API_KEY')
if not api_key:
    raise ValueError("Missing OpenAI API Key. Please set the OPENAI_API_KEY environment variable.")
openai.api_key = api_key

# ✅ Convert total duration from seconds to hours-minutes format
def format_duration(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}h {minutes}m"

# ✅ Process data from Google Sheet
sheet = gc.open(sheet_name).sheet1  # Open the first sheet
data = sheet.get_all_records()
df = pd.DataFrame(data)

# ✅ Exclude specific individuals
df = df[~df["First Name"].isin(["Cody", "Hannah", "Shannon", "Clinton"])]

# ✅ Ensure the column for Call Efficiency exists
df["% Calls >0.2 min"] = 100 - df["% Calls <0.2 min"]

# ✅ Identify top performers
top_calls = df.nlargest(3, "Total Calls")[["First Name", "Last Name", "Total Calls"]]
top_incall_avg = df.nlargest(3, "Total In Call Average")[["First Name", "Last Name", "Total In Call Average"]]
top_efficiency = df.nlargest(3, "% Calls >0.2 min")[["First Name", "Last Name", "% Calls >0.2 min"]]

# ✅ Identify underperformers
call_volume_threshold = 150
avg_calls = df["Total Calls"].mean()
short_call_threshold = df["% Calls <0.2 min"].mean()

total_gaps_30_avg = df["Number of Gaps (30+ min)"].mean()
total_gaps_15_avg = df["Number of Gaps (15-30 min)"].mean()

underperformers = df[
    (df["Total Calls"] < call_volume_threshold) |
    (df["Total Calls"] < avg_calls * 0.75) |
    (df["% Calls <0.2 min"] > short_call_threshold * 1.5)
]

# Ensure the columns are treated as datetime
if not pd.api.types.is_datetime64_any_dtype(df["First Call"]):
    df["First Call"] = pd.to_datetime(df["First Call"], format="%I:%M %p", errors="coerce")

if not pd.api.types.is_datetime64_any_dtype(df["Last Call Complete"]):
    df["Last Call Complete"] = pd.to_datetime(df["Last Call Complete"], format="%I:%M %p", errors="coerce")

# Check if parsing worked
if df["First Call"].isna().sum() > 0 or df["Last Call Complete"].isna().sum() > 0:
    print("⚠️ Warning: Some time values could not be parsed. Check for inconsistencies.")
    print(df[df["First Call"].isna() | df["Last Call Complete"].isna()])

# Ensure there are valid datetime values before proceeding
if df["First Call"].notna().sum() == 0 or df["Last Call Complete"].notna().sum() == 0:
    raise ValueError("Error: All values in 'First Call' or 'Last Call Complete' are NaT after conversion. Check your data format.")

# Drop only rows where both values are NaT
df = df.dropna(subset=["First Call", "Last Call Complete"], how="all")

# Find earliest and latest callers
earliest_caller = df.loc[df["First Call"].idxmin(), ["First Name", "Last Name", "First Call"]]
latest_caller = df.loc[df["Last Call Complete"].idxmax(), ["First Name", "Last Name", "Last Call Complete"]]

gaps_30_plus = df.nlargest(5, "Number of Gaps (30+ min)")[["First Name", "Last Name", "Number of Gaps (30+ min)"]]
gaps_15_30 = df.nlargest(5, "Number of Gaps (15-30 min)")[["First Name", "Last Name", "Number of Gaps (15-30 min)"]]

# ✅ Prepare statistics for OpenAI analysis
stats_summary = {
    "Top Performers": {
        "Total Calls": top_calls.to_dict(orient="records"),
        "Highest Average In-Call Time": top_incall_avg.to_dict(orient="records"),
        "Highest Call Efficiency": top_efficiency.to_dict(orient="records"),
    },
    "Underperformers": underperformers.to_dict(orient="records"),
    "Time Utilization": {
        "Earliest Caller": earliest_caller.to_dict(),
        "Latest Caller": latest_caller.to_dict(),
        "Frequent Gaps (30+ min)": gaps_30_plus.to_dict(orient="records"),
        "Frequent Gaps (15-30 min)": gaps_15_30.to_dict(orient="records"),
    }
}

# ✅ Generate email summary using OpenAI API
client = openai.OpenAI(api_key=api_key)
response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    max_tokens=2000,
    temperature=0.4,
    messages=[
        {"role": "system", "content": "Generate a visually appealing and well-structured HTML daily summary email for team leaders based on the provided SDR performance statistics."},
        {"role": "user", "content": """
Please generate a **professionally formatted** SDR performance summary that is **ready to be copied and pasted into an email**. Ensure the following:

- Use **HTML formatting and styles** to improve readability.
- Add a 2 rem gutter to the sides of the content.
- Capitalize section titles and separate them with **line breaks**.
- **Icons (🔥, ⚠, ⏳) to highlight key points**.
- Format performance numbers in a **clean and readable manner**.
- Maintain a **structured, left-aligned, styled tables** for clarity.
- Include **key action items for team leaders** at the end.
- Do NOT use the word "Team," this is a company-wide report.
- Keep the content under 3000 words.

Here is the SDR performance data:
""" + str(stats_summary)}
    ]
)

# ✅ Extract the generated content
daily_email_summary = response.choices[0].message.content

# ✅ Retrieve the Google Sheets URL from the environment variable
spreadsheet_url = os.getenv("SPREADSHEET_URL")
report_link = f'<p>Want to see more detail? <a href="{spreadsheet_url}" target="_blank">Go to the detailed report</a>.</p>'
if report_link not in daily_email_summary:
    daily_email_summary += f'<hr>{report_link}'

# ✅ Output the email summary for sending
print(daily_email_summary)

"""## Setting Up Email Credentials
This cell sets environment variables for the email sender credentials.

🔹 **Ensure you replace the placeholder with your actual email credentials before running this cell.**

"""

# Commented out IPython magic to ensure Python compatibility.
# %env EMAIL_USER=kate.fedotova@prophetlogic.com
# %env EMAIL_PASS=xdyc rokv cqyr vhrt

"""## Sending the SDR Performance Summary via Email
This cell:
- Composes an HTML email containing the daily SDR performance summary.
- Sends the email to predefined recipients.

🔹 **Ensure that the email credentials are set up correctly before running this cell.**

"""

import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta

# ✅ Load email credentials from environment variables
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

if not EMAIL_USER or not EMAIL_PASS:
    raise ValueError("❌ Missing EMAIL_USER or EMAIL_PASS environment variables!")

# ✅ Get yesterday's date in the format YYYY-MM-DD
yesterday_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

# ✅ Email configuration
SMTP_SERVER = "smtp.gmail.com"  # Change this for Outlook, Yahoo, etc.
SMTP_PORT = 587  # 465 for SSL, 587 for TLS
EMAIL_RECEIVERS = ["kate.fedotova@prophetlogic.com"]
EMAIL_SUBJECT = f"Daily SDR Performance Summary - {yesterday_date}"

# ✅ Create the email message
msg = MIMEMultipart()
msg["From"] = EMAIL_USER
msg["To"] = ", ".join(EMAIL_RECEIVERS)
msg["Subject"] = EMAIL_SUBJECT
msg.attach(MIMEText(daily_email_summary, "html"))

# ✅ Send the email securely
try:
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()  # Secure connection
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, EMAIL_RECEIVERS, msg.as_string())
    print(f"✅ Email sent successfully! Subject: {EMAIL_SUBJECT}")
except Exception as e:
    print(f"❌ Error sending email: {e}")
