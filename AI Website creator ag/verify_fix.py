import json
from app import template_generator

def test_industry_detection():
    # Test case: Bike description with a word containing 'eat' (treat)
    test_data = {
        "website_name": "Velosmith",
        "website_type": "Bike Shop",
        "description": "We offer the best treats for your carbon fiber bike.",
        "color_theme": "#e11d48",
        "images": []
    }
    
    print("Testing Industry Detection for 'Bike' with description containing 'treat'...")
    try:
        result = template_generator(test_data)
        
        # Check if the result contains bike-specific services
        # If the bug is fixed, we should see "Custom Builds" or "Professional Tuning"
        # If the bug exists, we see "Italian Dishes" or "Home Delivery"
        
        is_bike = "Custom Builds" in result['html']
        is_food = "Italian Dishes" in result['html']
        
        if is_bike and not is_food:
            print("✅ SUCCESS: Correctly detected 'bike' industry.")
        elif is_food:
            print("❌ FAILURE: Incorrectly detected 'restaurant' industry (substring match error).")
        else:
            print("❌ FAILURE: Unknown detection result.")
            
        with open('industry_test_out.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
            
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")

if __name__ == "__main__":
    test_industry_detection()
