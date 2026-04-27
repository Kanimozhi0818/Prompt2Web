import json
from app import template_generator

def verify_dynamic_content():
    # ── Test Restaurant Gallery ────────────────────────────────
    print("\nTesting 'Restaurant' Gallery...")
    res_rest = template_generator({"prompt": "Luxury restaurant", "website_name": "Luxe Dining", "website_type": "restaurant"})
    html_rest = res_rest["html"]
    
    if "Signature Pizza" in html_rest or "Pizza" in html_rest:
        print("✅ SUCCESS: Found topic-specific Restaurant project (Pizza).")
    if "Decadent Desserts" in html_rest and "Sweet" in html_rest:
        print("✅ SUCCESS: Found topic-specific Restaurant project (Desserts).")

    # ── Test Gym Testimonials ─────────────────────────────────
    print("\nTesting 'Gym' Testimonials...")
    res_gym = template_generator({"prompt": "Modern fitness gym", "website_name": "Iron Haven", "website_type": "gym"})
    html_gym = res_gym["html"]
    
    if "Rahul Sharma" in html_gym and "Gym Member" in html_gym:
        print("✅ SUCCESS: Found topic-specific Gym testimonial (Rahul Sharma).")
    if "Priya Kapoor" in html_gym and "Fitness Enthusiast" in html_gym:
        print("✅ SUCCESS: Found topic-specific Gym testimonial (Priya Kapoor).")

    # ── Test Coffee Gallery & Testimonials ──────────────────────────────
    print("\nTesting 'Coffee' Gallery & Testimonials...")
    res_coffee = template_generator({"prompt": "Cozy coffee shop", "website_name": "Bean Haven", "website_type": "coffee"})
    html_coffee = res_coffee["html"]
    
    if "Emily Brown" in html_coffee and "Coffee Lover" in html_coffee:
        print("✅ SUCCESS: Found topic-specific Coffee testimonial (Emily Brown).")
    if "Sophia Wilson" in html_coffee and "Food Blogger" in html_coffee:
        print("✅ SUCCESS: Found topic-specific Coffee testimonial (Sophia Wilson).")

    # ── Test About Section Layouts ────────────────────────────
    print("\nTesting About Section Layouts...")
    layouts_found = set()
    for i in range(10):
        res = template_generator({"prompt": "Coffee shop", "website_name": f"Cafe {i}", "website_type": "coffee"})
        html = res["html"]
        if "about-grid-reverse" in html:
            layouts_found.add("image-right")
        elif "about-centered" in html:
            layouts_found.add("centered")
        elif "about-grid" in html:
            layouts_found.add("image-left")
    
    print(f"Layouts found in 10 runs: {layouts_found}")
    if len(layouts_found) > 1:
        print(f"✅ SUCCESS: Found {len(layouts_found)} different About layouts.")
    else:
        print("❌ FAILURE: Only one About layout found. Randomization might be broken.")

    # ── Test Topic-Specific About Content ─────────────────────
    print("\nTesting 'Gym' About Content...")
    res_gym_about = template_generator({"prompt": "Hardcore bodybuilding gym", "website_name": "Power Gym", "website_type": "gym"})
    html_gym_about = res_gym_about["html"]
    
    gym_keywords = ["fitness", "training", "workout", "health", "strength", "gym"]
    found_keywords = [kw for kw in gym_keywords if kw.lower() in html_gym_about.lower()]
    print(f"Gym keywords found: {found_keywords}")
    if len(found_keywords) >= 2:
        print("✅ SUCCESS: Found topic-specific About content for Gym.")
    else:
        print("❌ FAILURE: Gym About content seems generic.")

    with open("final_verify_out.json", "w", encoding="utf-8") as f:
        json.dump(res_gym_about, f, indent=2)

    print("\nVerification Complete.")

if __name__ == "__main__":
    verify_dynamic_content()
