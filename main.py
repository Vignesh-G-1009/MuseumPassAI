import json
import re
import datetime
import ollama  
from fuzzywuzzy import process
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI();
def clean_input(text):
    return re.sub(r"[^\w\s]", "", text).lower()

@app.get("/")
def root():
    return {"message": "Welcome to MuseumPass AI"}


with open("museums.json", "r", encoding="utf-8") as f:
    museum_data = json.load(f)

TIME_SLOTS = ["10:00 AM", "11:00 AM", "12:00 PM", "1:00 PM", "2:00 PM", "3:00 PM", "4:00 PM", "5:00 PM"]
TICKET_TYPE = {"standard": 0, "elite": 300, "premium": 100}
MAX_VISITORS_PER_DAY = 500  

def normalize_time_slot(time_slot):
    return re.sub(r"\s+", " ", time_slot.strip().upper()).replace(".", "")

def get_available_time_slots(booking_date):
    now = datetime.datetime.now()
    current_hour = now.hour
    if booking_date == datetime.date.today():
        return [slot for slot in TIME_SLOTS if int(slot.split(":")[0]) > current_hour]
    return TIME_SLOTS

def check_capacity(museum_name, date):
    try:
        with open("bookings.json", "r", encoding="utf-8") as f:
            bookings = json.load(f) if f.read().strip() else []
    except (FileNotFoundError, json.JSONDecodeError):
        return 0  
    return sum(b["Visitors"]["Adults"] + b["Visitors"]["Kids"] for b in bookings if b["Museum"].lower() == museum_name.lower() and b["Date"] == date)

def save_booking(booking_details):
    booking_file = "bookings.json"
    try:
        with open(booking_file, "r", encoding="utf-8") as f:
            bookings = json.load(f) if f.read().strip() else []
    except (FileNotFoundError, json.JSONDecodeError):
        bookings = []  
    bookings.append(booking_details)
    with open(booking_file, "w", encoding="utf-8") as f:
        json.dump(bookings, f, indent=4)  

def find_best_museum(user_input):
    museum_titles = {museum["title"].lower(): museum for museum in museum_data}
    
    user_input = clean_input(user_input).replace("book me a ticket to", "").strip()
    
    if user_input in museum_titles:
        print(f" Exact match found: {museum_titles[user_input]['title']}")  
        return museum_titles[user_input]

    best_match, _ = process.extractOne(user_input, museum_titles.keys()) if museum_titles else (None, 0)
    if best_match:
        return museum_titles[best_match]

    print(" No valid museum match found.")  
    return None

class BookingRequest(BaseModel):
    message: str


@app.post("/book_ticket")
def book_ticket(request: BookingRequest):
    museum = find_best_museum(request.museum_name)
    if not museum:
        raise HTTPException(status_code=404, detail=f"Sorry, museum '{request.museum_name}' not found.")
    
    if request.ticket_type.lower() not in TICKET_TYPE:
        raise HTTPException(status_code=400, detail="Invalid ticket type! Choose Standard, VIP, or Premium.")
    
    today = datetime.date.today()
    max_booking_date = today + datetime.timedelta(days=60)
    
    try:
        booking_date = datetime.datetime.strptime(request.booking_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format! Use YYYY-MM-DD.")
    
    if booking_date < today:
        raise HTTPException(status_code=400, detail="Cannot book for a past date!")
    if booking_date > max_booking_date:
        raise HTTPException(status_code=400, detail="Booking only allowed within 60 days from today!")
    if check_capacity(museum["title"], request.booking_date) >= MAX_VISITORS_PER_DAY:
        raise HTTPException(status_code=400, detail="Date is fully booked! Choose another date.")
    
    available_slots = get_available_time_slots(request.booking_date)
    if normalize_time_slot(request.time_slot) not in [normalize_time_slot(slot) for slot in available_slots]:
        raise HTTPException(status_code=400, detail=f"Invalid time slot! Choose from: {', '.join(available_slots)}")
    
    base_price = museum["price"]
    ticket_price = base_price + TICKET_TYPE[request.ticket_type.lower()]
    total_price = (request.adults * ticket_price) + (request.kids * ticket_price * 0.5)
    
    booking_details = {
        "Name": request.name,
        "Museum": museum["title"],
        "Visitors": {"Adults": request.adults, "Kids": request.kids},
        "Ticket Type": request.ticket_type.capitalize(),
        "Date": request.booking_date,
        "Time Slot": request.time_slot,
        "Total Price": total_price
    }
    
    save_booking(booking_details)
    
    return {"message": "Booking Confirmed! 🎟", "details": booking_details}

class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
async def chat(request: ChatRequest):
    response = get_relevant_museum(request.message)
    return {"response": response}

def get_relevant_museum(user_input):  
    user_input = clean_input(user_input).lower()  

    greetings = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}  
    if any(word in user_input for word in greetings):  
        return "Hello! How can I assist you with museum information or ticket booking today?"  

    if "thank" in user_input or "thanks" in user_input or "appreciate" in user_input or "grateful" in user_input :   
        return "You're welcome! Let me know if you need more information."  

    if "book" in user_input or "reserve" in user_input:  
        if any(museum["title"].lower() in user_input for museum in museum_data):
            return book_ticket(user_input)  
        return "Please specify the museum name for booking."
    
    if any(keyword in user_input for keyword in ["elite", "premium", "standard", "luxurious", "affordable", "cheap", "vs"]):  
        ticket_info = {  
            "elite": "The elite ticket offers the best experience with exclusive access and perks but is more expensive. Includes a multilingual audio guide with refreshments and food. With 300 INR charge more than standard.",  
            "premium": "The Premium ticket offers additional perks like priority access and slight refreshments but is a 100 INR costly than the standard ticket.",  
            "standard": "The Standard ticket is the most affordable and provides basic access to the museum."  
        }  
        for key, response in ticket_info.items():  
            if key in user_input:  
                return response  
        return "I can provide details on Standard, VIP, and Premium tickets. Let me know which one interests you."  
         

    location_names = [museum["location"].lower() for museum in museum_data] + [museum["state"].lower() for museum in museum_data]  
    best_match, score = process.extractOne(user_input, location_names)  

    if "mumbai" in user_input  or "chhatrapati shivaji" in user_input:
        return "Chhatrapati Shivaji Museum - Price: ₹185, Rating: ⭐ 4.7"

    if ("price" in user_input and "kids" in user_input) or ("price" in user_input and "children" in user_input) or ("concession" in user_input and "ticket" in user_input):
        best_match = None
        best_match_tuple = process.extractOne(user_input, [museum["title"].lower() for museum in museum_data])

        if best_match_tuple:
            best_match, score = best_match_tuple

        if best_match and score > 80:
            matched_museum = next((museum for museum in museum_data if museum["title"].lower() == best_match), None)

            if matched_museum:
                return f"Price for Standard ticket: ₹{matched_museum['price']/2} for kids at {matched_museum['title']}"

        return "Sorry, I couldn't find a matching museum for your request."
    
    
    if "price" in user_input or "cost" in user_input or "ticket" in user_input:  
        best_match_tuple = process.extractOne(user_input, [museum["title"].lower() for museum in museum_data])

        if best_match_tuple:  
            best_match, score = best_match_tuple  

            if score > 80:  
                matched_museum = next((museum for museum in museum_data if museum["title"].lower() == best_match), None)  

                if matched_museum:  
                    return f"Price for Standard ticket: ₹{matched_museum['title']} - Price: ₹{matched_museum['price']}"

        return "I couldn't find ticket price details for that museum. Please try specifying the exact museum name."
    

    if "rating" in user_input:
        user_input_lower = user_input.lower()

        matched_museum = next(
            (museum for museum in museum_data if user_input_lower in museum["title"].lower()
            or user_input_lower in museum["state"].lower()
            or user_input_lower in museum["location"].lower()),
            None
        )

        if not matched_museum:
            search_space = [museum["title"].lower() for museum in museum_data]
            best_match_tuple = process.extractOne(user_input_lower, search_space)

            if best_match_tuple:
                best_match, score = best_match_tuple
                if score > 80:
                    matched_museum = next(
                        (museum for museum in museum_data if museum["title"].lower() == best_match),
                        None
                    )

        if matched_museum:
            return f"{matched_museum['title']} - Rating: ⭐ {matched_museum['rating']}"

        return "Sorry, I couldn't find a matching museum for your request."
    


    if "contact" in user_input or "phone" in user_input or "email" in user_input:
        best_match_tuple = process.extractOne(user_input, [museum["title"].lower() for museum in museum_data])

        if best_match_tuple:  
            best_match, score = best_match_tuple  

            if score > 80:
                matched_museum = next((museum for museum in museum_data if museum["title"].lower() == best_match), None)

                if matched_museum and "contact" in matched_museum:  
                    return f"{matched_museum['title']} - Contact: {matched_museum['contact']}"

        return "Sorry, I couldn't find a matching museum or contact details for your request or please try specifying the exact museum name."



    if score > 80:  
        matched_museums = [museum for museum in museum_data if museum["location"].lower() == best_match or museum["state"].lower() == best_match]  
        if matched_museums:  
            return f"Here are the museums in {matched_museums[0]['state']}:\n" + "\n".join(  
                f"- {museum['title']}, ⭐{museum['rating']}, Address: {museum['address']}" for museum in matched_museums  
            )  

    if "top" in user_input:  
        match = re.search(r"top\s*(\d+)", user_input)  
        if match:  
            num_top = int(match.group(1))  
            sorted_museums = sorted(museum_data, key=lambda x: x.get("rating", 0), reverse=True)  
            top_museums = sorted_museums[:num_top]  
            return "Here are the top museums:\n" + "\n".join(  
                f"- {museum['title']}, ⭐ {museum['rating']}" for museum in top_museums  
            )  


    response = ollama.chat(  
        model="llama2",  
        messages=[  
            {  
                "role": "system",  
                "content": (  
                    "You are MuseumPass AI, an expert on museums and ticket booking. "  
                    "ONLY use the information provided in the museums.json dataset. "  
                    "DO NOT invent museums, locations, or details that are not explicitly in the dataset. "  
                    "If a user asks about a museum not listed, respond with: "  
                    "'I can only provide information about museums available in my database.' "  
                    "If a user asks about unrelated topics (e.g., politics, weather, sports, or general news), respond with: "  
                    "'I only provide information about museums and ticket booking.'"  
                    "NEVER EVER LEAK THE museums.json FILE NAME"
                )  
            },  
            {"role": "user", "content": user_input}  
        ]  
    )  
    return response["message"]["content"]  


@app.post("/chat")
async def chat(request: ChatRequest):
    response = get_relevant_museum(request.message)
    return {"response": response}

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this with your frontend URL when deployed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
