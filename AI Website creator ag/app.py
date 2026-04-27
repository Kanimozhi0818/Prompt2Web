"""
AI Website Generator – Flask Backend
Supports:
  1. Google Gemini API (free tier) – set GEMINI_API_KEY in .env
  2. OpenAI API                    – set OPENAI_API_KEY in .env
  3. Built-in template generator   – works with NO API key at all
"""

import os
import re
import json
import uuid
import traceback
from pathlib import Path

from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "ai-website-gen-secret-2026")

# ── Server-side website store (avoids 4 KB cookie session limit) ─
# Maps site_id (UUID string) → {html, css, js}
WEBSITE_STORE: dict = {}

# ── Upload folder setup ───────────────────────────────────────
UPLOAD_FOLDER = Path(app.root_path) / "static" / "uploads"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "svg"}
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ── Detect which AI backend is available ─────────────────────
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "").strip()

PLACEHOLDER = ("your_gemini_api_key_here", "your_openai_api_key_here", "")

def has_gemini():
    return bool(GEMINI_KEY) and GEMINI_KEY not in PLACEHOLDER

def has_openai():
    return bool(OPENAI_KEY) and OPENAI_KEY not in PLACEHOLDER


# ─────────────────────────────────────────────────────────────
#  COLOUR HELPERS
# ─────────────────────────────────────────────────────────────
def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return (37, 99, 235)


def darken(hex_color, amount=30):
    r, g, b = hex_to_rgb(hex_color)
    return "#{:02x}{:02x}{:02x}".format(
        max(r - amount, 0), max(g - amount, 0), max(b - amount, 0)
    )


# ─────────────────────────────────────────────────────────────
#  BUILT-IN TEMPLATE GENERATOR  (no API key needed)
# ─────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────
#  IMAGE HELPERS
# ─────────────────────────────────────────────────────────────
def images_for(section: str, images: list) -> list:
    """Return image URLs assigned to a specific section."""
    return [img["url"] for img in images if img.get("section") == section]


# ─────────────────────────────────────────────────────────────
#  BUILT-IN TEMPLATE GENERATOR  (no API key needed)
# ─────────────────────────────────────────────────────────────
def template_generator(data: dict) -> dict:
    name   = data.get("website_name", "MyBusiness")
    btype  = data.get("website_type", "business")
    desc   = data.get("description",  "We deliver outstanding results.")
    color  = data.get("color_theme",  "#2563eb").strip() or "#2563eb"
    dark   = darken(color)
    images = data.get("images", [])  # list of {url, section}

    # ── Collect images per section ────────────────────────────
    hero_imgs     = images_for("hero",     images)
    about_imgs    = images_for("about",    images)
    service_imgs  = images_for("services", images)
    gallery_imgs  = images_for("gallery",  images)
    contact_imgs  = images_for("contact",  images)

    # ── Resolve Design Profile ────────────────────────────────
    profile = resolve_design_profile(btype, data.get('color_theme', 'blue'))
    primary = profile['primary']
    font_h  = profile['font_heading']
    font_b  = profile['font_body']
    h_title = profile['hero_title']
    s_layout = profile.get('service_layout', 'icon-cards')

    # ── Hero background style ─────────────────────────────────
    if hero_imgs:
        hero_bg_style = f'background-image:url({hero_imgs[0]});background-size:cover;background-position:center;'
    else:
        hero_bg_style = ''

    # ── About image block ─────────────────────────────────────
    if about_imgs:
        about_img_block = f'<img src="{about_imgs[0]}" alt="About {name}" style="width:100%;height:380px;object-fit:cover;border-radius:14px;">'
    else:
        about_img_block = '<div class="img-box">🏢</div>'

    # ── Industry-specific services (fallback logic) ───────────
    industry_services = {
        "coffee": [
            ("☕", "Espresso Coffee", "Freshly brewed premium beans from around the world."),
            ("🥐", "Fresh Bakery", "Hand-crafted pastries baked daily in our kitchen."),
            ("🍰", "Signature Desserts", "Sweet treats made with love and the finest ingredients."),
            ("📶", "Free WiFi", "Stay connected with our high-speed guest network."),
            ("🪑", "Cozy Seating", "Comfortable corners perfect for work or relaxation."),
            ("🚚", "Takeaway", "Order ahead for a quick and fresh pickup.")
        ],
        "gym": [
            ("🏋️", "Personal Training", "One-on-one sessions tailored to your fitness goals."),
            ("💪", "Strength Training", "Professional equipment for building power and muscle."),
            ("🧘", "Yoga Classes", "Find your balance with our expert-led yoga sessions."),
            ("🥗", "Nutrition Plans", "Fuel your body with custom meal prep and guidance."),
            ("🔥", "Fat Loss", "High-intensity programs designed to burn calories fast."),
            ("🏃", "Cardio Training", "State-of-the-art treadmills and elliptical zones.")
        ],
        "restaurant": [
            ("🍕", "Italian Dishes", "Authentic recipes passed down through generations."),
            ("🍝", "Pasta Menu", "Freshly made pasta with rich, homemade sauces."),
            ("🚚", "Home Delivery", "Hassle-free delivery straight to your doorstep."),
            ("🍰", "Fine Desserts", "The perfect sweet ending to every meal."),
            ("🍷", "Exquisite Drinks", "A curated selection of wines and craft beverages."),
            ("🥗", "Fresh Salads", "Organic ingredients sourced from local farms.")
        ],
        "portfolio": [
            ("💻", "Web Development", "Building fast, modern, and scalable web applications."),
            ("🎨", "UI Design", "Creating beautiful and intuitive user interfaces."),
            ("📱", "Responsive", "Optimized experiences across all mobile devices."),
            ("🚀", "Project Management", "End-to-end delivery from concept to launch."),
            ("🧠", "Problem Solving", "Strategic thinking for complex technical challenges."),
            ("📈", "Performance", "Speed optimization for superior user retention.")
        ],
        "bike": [
            ("🚲", "Custom Builds", "Dream bikes built from the frame up to your exact specs."),
            ("🔧", "Professional Tuning", "Precision adjustments to keep your ride smooth and fast."),
            ("🏁", "Race Preparation", "Optimizing every component for peak competitive performance."),
            ("🛞", "Wheel Building", "Hand-built wheels for ultimate strength and reliability."),
            ("🧤", "Premium Gear", "Curation of the world's best cycling apparel and accessories."),
            ("🧼", "Performance Wash", "Deep cleaning and lubrication to extend your bike's life.")
        ]
    }

    selected_services = []
    desc_lower = (btype + " " + desc).lower()
    
    # Use word boundary matching to avoid false positives (e.g., 'eat' in 'treat')
    def has_any(words, keywords):
        return any(k in words for k in keywords)

    # Simple tokenization
    tokens = set(re.findall(r'\w+', desc_lower))

    if has_any(tokens, ["coffee", "cafe", "espresso", "latte"]):
        selected_services = industry_services["coffee"]
    elif has_any(tokens, ["gym", "fitness", "training", "workout"]):
        selected_services = industry_services["gym"]
    elif has_any(tokens, ["restaurant", "food", "eat", "diner", "bistro", "pizza"]):
        selected_services = industry_services["restaurant"]
    elif has_any(tokens, ["portfolio", "dev", "design", "creative", "freelance"]):
        selected_services = industry_services["portfolio"]
    elif has_any(tokens, ["bike", "cycle", "bicycle", "motorcycle", "cycling"]):
        selected_services = industry_services["bike"]
    else:
        # Default generic but better than before
        selected_services = [
            ("⭐", "Top Quality", "We maintain the highest standards in every project."),
            ("🚀", "Global Delivery", "Bringing our services to you with speed and care."),
            ("🤝", "Expert Advice", "Our professionals are ready to help you thrive."),
            ("💡", "Smart Ideas", "Innovative solutions for modern business needs."),
            ("🔒", "Safe & Secure", "Reliable foundations you can always trust."),
            ("📈", "Proven Growth", "Results-driven strategies for long-term success.")
        ]

    topic = btype if btype else "business"
    svc_html = ""
    svc_container_cls = "service-grid"
    
    if s_layout == "icon-cards":
        svc_container_cls = "service-grid"
        for icon, title, text in selected_services:
            svc_html += f'<div class="card icon-card pulse-hover"><div class="card-icon">{icon}</div><h3>{title}</h3><p>{text}</p></div>'
    elif s_layout == "image-cards":
        svc_container_cls = "service-grid"
        for i, (icon, title, text) in enumerate(selected_services):
            img_url = f"https://loremflickr.com/600/400/{topic}/all?random={i}"
            svc_html += f'<div class="card img-card slide-in"><div class="card-img"><img src="{img_url}" alt="{title}" style="width:100%;height:200px;object-fit:cover;border-radius:var(--r) var(--r) 0 0;"></div><div class="card-body" style="padding:1.5rem;"><h3>{title}</h3><p>{text}</p></div></div>'
    elif s_layout == "text-list":
        svc_container_cls = "service-list"
        for icon, title, text in selected_services:
            svc_html += f'<div class="list-item fade-in"><h3>{icon} {title}</h3><p>{text}</p></div>'
    elif s_layout == "animated-slider":
        svc_container_cls = "service-slider-wrap"
        slider_inner = ""
        for icon, title, text in selected_services:
            slider_inner += f'<div class="slider-item card"><div class="card-icon">{icon}</div><h3>{title}</h3><p>{text}</p></div>'
        svc_html = f'<div class="slider-track">{slider_inner}{slider_inner}</div>' # Double for seamless loop
    elif s_layout == "hover-cards":
        svc_container_cls = "service-grid hover-effect-grid"
        for icon, title, text in selected_services:
            svc_html += f'<div class="card hover-card-v2"><div class="card-icon">{icon}</div><h3>{title}</h3><p>{text}</p></div>'
    elif s_layout == "horizontal-scroll":
        svc_container_cls = "service-scroll-container"
        for icon, title, text in selected_services:
            svc_html += f'<div class="scroll-card card"><div class="card-icon">{icon}</div><h3>{title}</h3><p>{text}</p></div>'
    else:
        # Fallback to standard
        for icon, title, text in selected_services:
            svc_html += f'<div class="card"><div class="card-icon">{icon}</div><h3>{title}</h3><p>{text}</p></div>'

    # ── Industry-specific image/logic ─────────────────────────
    hero_img_url = f"https://images.unsplash.com/photo-1542744173-8e7e53415bb0?auto=format&fit=crop&w=1600&q=80" # Default
    if hero_imgs:
        hero_img_url = hero_imgs[0]
    else:
        # Generate high-quality Unsplash URL from randomized query
        hero_img_url = f"https://loremflickr.com/1600/900/{profile['hero_img_query']}/all"

    # Button CSS class
    btn_cls = "rounded"
    if profile['hero_btn_style'] == "pill": btn_cls = "pill"
    elif profile['hero_btn_style'] == "outline": btn_cls = "outline"
    elif profile['hero_btn_style'] == "square-bold": btn_cls = "square-bold"
    elif profile['hero_btn_style'] == "glass": btn_cls = "glass"

    # Hero Layout HTML
    hero_layout = profile['hero_layout']
    hero_inner_html = ""
    if "split" in hero_layout:
        side = "left" if "left" in hero_layout else "right"
        hero_inner_html = f"""
    <div class="hero-split {side}">
      <div class="hero-content fade-in">
        <p class="hero-tag">Welcome to {name}</p>
        <h1 id="hero-heading">{h_title}</h1>
        <p class="hero-sub">{desc}</p>
        <div class="hero-btns">
          <a href="#contact" class="btn btn-primary {btn_cls}">Get Started</a>
          <a href="#about" class="btn btn-outline {btn_cls}">Learn More</a>
        </div>
      </div>
      <div class="hero-media"><img src="{hero_img_url}" alt="Hero Image"></div>
    </div>"""
    else: # Default centered
        hero_inner_html = f"""
    <div class="hero-body fade-in">
      <p class="hero-tag">Welcome to {name}</p>
      <h1 id="hero-heading">{h_title}</h1>
      <p class="hero-sub">{desc}</p>
      <div class="hero-btns">
        <a href="#contact" class="btn btn-primary {btn_cls}">Get Started</a>
        <a href="#about" class="btn btn-outline {btn_cls}">Learn More</a>
      </div>
    </div>"""
    
    hero_bg_style = f"background-image: linear-gradient(rgba(0,0,0,0.5), rgba(0,0,0,0.5)), url('{hero_img_url}'); background-size: cover; background-position: center;" if "split" not in hero_layout else ""

    # ── Gallery logic ─────────────────────────────────────────
    gallery_items = []
    # Use AI-suggested images if provided, else use profile defaults with high-res Unsplash
    if gallery_imgs:
        for i, url in enumerate(gallery_imgs[:6]):
            # Try to match AI image with a profile title if available
            g_item = profile['gallery_items'][i] if i < len(profile['gallery_items']) else {"title": f"Project {i+1}", "label": "Photography"}
            gallery_items.append(
                f'<div class="gallery-item">'
                f'<img src="{url}" alt="{g_item["title"]}" style="width:100%;height:100%;object-fit:cover;">'
                f'<div class="overlay"><span>{g_item["title"]}</span><p>{g_item["label"]}</p></div></div>'
            )
    else:
        # Generate 6 unique cards from profile items
        for i, item in enumerate(profile['gallery_items'][:6]):
            img_url = f"https://loremflickr.com/600/400/{item['img_query']}/all?random={i}"
            gallery_items.append(
                f'<div class="gallery-item">'
                f'<img src="{img_url}" alt="{item["title"]}" style="width:100%;height:100%;object-fit:cover;">'
                f'<div class="overlay"><span>{item["title"]}</span><p>{item["label"]}</p></div></div>'
            )
    
    gallery_html = ''.join(gallery_items)

    # ── Contact banner image ──────────────────────────────────
    contact_banner = ''
    if contact_imgs:
        contact_banner = f'<div style="margin-bottom:2rem;border-radius:14px;overflow:hidden;"><img src="{contact_imgs[0]}" alt="Contact banner" style="width:100%;height:220px;object-fit:cover;"></div>'

    # ── About Section Logic ────────────────────────────────────
    about_layout = profile.get('about_layout', 'image-left')
    about_paragraphs_html = "".join([f"<p>{p}</p>" for p in profile['about_p']])
    about_img_url = f"https://loremflickr.com/600/400/{profile['about_iq']}/all"
    if about_imgs:
        about_img_url = about_imgs[0]
    
    if about_layout == 'centered':
        about_html = f"""
        <div class="about-centered">
            <p class="label center">ABOUT US</p>
            <h2 class="center">Who We Are</h2>
            <div class="about-text-center">
                {about_paragraphs_html}
                <div class="center-btn-wrap">
                    <a href="#services" class="btn btn-primary">Our Services</a>
                </div>
            </div>
        </div>"""
    else:
        layout_class = "about-grid-reverse" if about_layout == 'image-right' else ""
        about_html = f"""
        <div class="about-grid {layout_class}">
            <div class="about-img"><img src="{about_img_url}" alt="About {name}" style="width:100%;height:380px;object-fit:cover;border-radius:14px;"></div>
            <div class="about-text">
                <p class="label">ABOUT US</p>
                <h2 id="about-heading">Who We Are</h2>
                <div id="about-para">
                    {about_paragraphs_html}
                </div>
                <a href="#services" class="btn btn-primary">Our Services</a>
            </div>
        </div>"""

    # ── Testimonials logic ────────────────────────────────────
    t_layout = profile.get('testi_layout', 'card-grid')
    testi_items = []
    for i, item in enumerate(profile.get('testimonials', [])[:3]):
        initials = "".join([n[0] for n in item['name'].split()[:2]]).upper()
        # Portrait avatar from Unsplash/LoremFlickr
        avatar_url = f"https://loremflickr.com/100/100/portrait?random={i}"
        
        if t_layout == "quote-centered":
            testi_items.append(
                f'<div class="testi-quote-item fade-in">'
                f'<div class="quote-icon">“</div>'
                f'<blockquote>{item["quote"]}</blockquote>'
                f'<cite>— {item["name"]}, <span>{item["role"]}</span></cite>'
                f'</div>'
            )
        elif t_layout == "image-beside":
            testi_items.append(
                f'<div class="testi-beside card pulse-hover fade-in">'
                f'<div class="testi-img"><img src="{avatar_url}" alt="{item["name"]}"></div>'
                f'<div class="testi-content">'
                f'<p>"{item["quote"]}"</p>'
                f'<strong>{item["name"]}</strong><span>{item["role"]}</span>'
                f'</div></div>'
            )
        elif t_layout == "glass-cards":
            testi_items.append(
                f'<div class="testi-card glass-card scale-hover fade-in">'
                f'<p>"{item["quote"]}"</p>'
                f'<div class="testi-author">'
                f'<img src="{avatar_url}" class="avatar-round" alt="{item["name"]}">'
                f'<div><strong>{item["name"]}</strong><span>{item["role"]}</span></div>'
                f'</div></div>'
            )
        elif t_layout == "slider-carousel":
            testi_items.append(
                f'<div class="testi-slide card pulse-hover">'
                f'<p>"{item["quote"]}"</p>'
                f'<div class="testi-author">'
                f'<div class="avatar">{initials}</div>'
                f'<div><strong>{item["name"]}</strong><span>{item["role"]}</span></div>'
                f'</div></div>'
            )
        else: # card-grid and fallback for parallax
            card_cls = "glass-card scale-hover" if t_layout == "parallax-bg" else "card pulse-hover"
            testi_items.append(
                f'<div class="testi-card {card_cls} fade-in">'
                f'<p>"{item["quote"]}"</p>'
                f'<div class="testi-author">'
                f'<div class="avatar">{initials}</div>'
                f'<div><strong>{item["name"]}</strong><span>{item["role"]}</span></div>'
                f'</div></div>'
            )
    
    testi_html = "".join(testi_items)
    if t_layout == "slider-carousel":
        testi_html = testi_html + testi_html # Double for seamless loop
    
    testi_container_cls = "testi-grid"
    if t_layout == "slider-carousel": testi_container_cls = "testi-slider-track"
    elif t_layout == "quote-centered": testi_container_cls = "testi-quotes-list"
    elif t_layout == "parallax-bg": testi_container_cls = "testi-parallax-wrap"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name}</title>
<link href="https://fonts.googleapis.com/css2?family={font_h.replace(' ', '+')}&family={font_b.replace(' ', '+')}&display=swap" rel="stylesheet">
<link rel="stylesheet" href="style.css">
<style>
  :root {{
    --primary: {primary};
    --primary-light: {primary}22;
    --font-h: '{font_h}', sans-serif;
    --font-b: '{font_b}', sans-serif;
  }}
  h1, h2, h3 {{ font-family: var(--font-h); }}
  body {{ font-family: var(--font-b); }}
  
  /* Dynamic Hero Layouts */
  .hero-split {{ display: grid; grid-template-columns: 1fr 1fr; min-height: 100vh; align-items: center; overflow: hidden; }}
  .hero-split.right {{ grid-template-columns: 1fr 1fr; }}
  .hero-split.right .hero-content {{ order: 2; padding: 4rem; }}
  .hero-split.right .hero-media {{ order: 1; }}
  .hero-split.left .hero-content {{ order: 1; padding: 4rem; }}
  .hero-split.left .hero-media {{ order: 2; }}
  .hero-media img {{ width: 100%; height: 100vh; object-fit: cover; }}
  
  /* About Layouts */
  .about-grid-reverse .about-img {{ order: 2; }}
  .about-grid-reverse .about-text {{ order: 1; }}
  .about-centered {{ max-width: 800px; margin: 0 auto; text-align: center; }}
  .about-text-center {{ font-size: 1.1rem; color: var(--muted); }}
  .center-btn-wrap {{ margin-top: 2rem; display: flex; justify-content: center; }}

  /* Button Styles */
  .btn.pill {{ border-radius: 50px; }}
  .btn.rounded {{ border-radius: 8px; }}
  .btn.square-bold {{ border-radius: 0; font-weight: 800; text-transform: uppercase; }}
  .btn.glass {{ background: rgba(255,255,255,0.1); backdrop-filter: blur(10px); color: white; border: 1px solid rgba(255,255,255,0.2); }}
  .btn.outline {{ background: transparent; border: 2px solid var(--primary); color: var(--primary); }}
  .btn.outline:hover {{ background: var(--primary); color: white; }}
</style>
</head>
<body>
<nav id="navbar">
  <div class="nav-inner">
    <div class="logo">{name}</div>
    <div class="burger" id="burger"><span></span><span></span><span></span></div>
    <ul class="nav-links" id="navLinks">
      <li><a href="#home">Home</a></li>
      <li><a href="#about">About</a></li>
      <li><a href="#services">Services</a></li>
      <li><a href="#gallery">Gallery</a></li>
      <li><a href="#testimonials">Testimonials</a></li>
      <li><a href="#contact">Contact</a></li>
    </ul>
  </div>
</nav>
<section id="home" class="hero" style="{hero_bg_style}">
  {hero_inner_html}
</section>
<section id="about" class="section">
  <div class="container fade-in">
    {about_html}
  </div>
</section>
</section>
<section id="services" class="section alt">
  <div class="container fade-in">
    <p class="label center">WHAT WE OFFER</p>
    <h2 class="center" id="services-heading">Our Services</h2>
    <div class="{svc_container_cls}" id="service-grid">
      {svc_html}
    </div>
  </div>
</section>
<section id="gallery" class="section">
  <div class="container fade-in">
    <p class="label center">PORTFOLIO</p>
    <h2 class="center">Our Work</h2>
    <div class="gallery-grid" id="gallery-grid">
      {gallery_html}
    </div>
  </div>
</section>
<section id="testimonials" class="section alt {'testi-parallax-section' if t_layout == 'parallax-bg' else ''}">
  <div class="container fade-in">
    <p class="label center">TESTIMONIALS</p>
    <h2 class="center">What Clients Say</h2>
    <div class="{testi_container_cls}" id="testimonial-container">
      {testi_html}
    </div>
  </div>
</section>
<section id="contact" class="section">
  <div class="container fade-in">
    <p class="label center">GET IN TOUCH</p>
    <h2 class="center" id="contact-heading">Contact Us</h2>
    {contact_banner}
    <div class="contact-wrap">
      <form id="cForm" class="contact-form">
        <div class="field-row">
          <div class="field"><input type="text" placeholder="Your Name" required></div>
          <div class="field"><input type="email" placeholder="Your Email" required></div>
        </div>
        <div class="field"><input type="text" placeholder="Subject"></div>
        <div class="field"><textarea rows="5" placeholder="Your Message" required></textarea></div>
        <button type="submit" class="btn btn-primary">Send Message</button>
      </form>
    </div>
  </div>
</section>
<footer class="footer">
  <div class="container footer-inner">
    <div class="footer-logo">{name}</div>
    <p>Providing exceptional {btype} services since 2020.</p>
    <p class="copy">&copy; 2026 {name}. All rights reserved.</p>
  </div>
</footer>
<script src="script.js"></script>
</body>
</html>"""

    css = f""":root{{--primary:{color};--dark:{dark};--text:#0f172a;--muted:#475569;--light:#94a3b8;--bg:#fff;--alt:#f8fafc;--border:#e2e8f0;--r:14px;--sh:0 4px 20px rgba(0,0,0,.08);--shl:0 20px 40px rgba(0,0,0,.12);--t:.3s cubic-bezier(.4,0,.2,1)}}
*,*::before,*::after{{margin:0;padding:0;box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{font-family:'Inter',sans-serif;color:var(--text);background:var(--bg);line-height:1.65;overflow-x:hidden}}a{{text-decoration:none;color:inherit}}
.btn{{display:inline-flex;align-items:center;gap:.4rem;padding:.8rem 1.9rem;border-radius:50px;font-weight:700;font-size:.95rem;border:none;cursor:pointer;font-family:inherit;transition:all var(--t)}}
.btn-primary{{background:var(--primary);color:#fff;box-shadow:0 4px 14px rgba(0,0,0,.2)}}.btn-primary:hover{{background:var(--dark);transform:translateY(-2px);box-shadow:0 8px 22px rgba(0,0,0,.25)}}
.btn-outline{{background:transparent;color:#fff;border:2px solid rgba(255,255,255,.7)}}.btn-outline:hover{{background:rgba(255,255,255,.15)}}
#navbar{{position:fixed;top:0;width:100%;background:rgba(255,255,255,.92);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);z-index:999;transition:box-shadow var(--t)}}#navbar.scrolled{{box-shadow:var(--shl)}}
.nav-inner{{max-width:1180px;margin:auto;padding:.9rem 5%;display:flex;align-items:center;justify-content:space-between}}
.logo{{font-size:1.5rem;font-weight:800;color:var(--primary)}}.nav-links{{list-style:none;display:flex;gap:1.75rem}}.nav-links a{{font-weight:600;font-size:.9rem;color:var(--text);transition:color var(--t)}}.nav-links a:hover{{color:var(--primary)}}
.burger{{display:none;flex-direction:column;gap:5px;cursor:pointer}}.burger span{{height:3px;width:26px;background:var(--text);border-radius:3px;transition:all var(--t)}}
.hero{{min-height:100vh;background:linear-gradient(135deg,var(--primary) 0%,var(--dark) 100%);display:flex;align-items:center;justify-content:center;text-align:center;padding:8rem 5% 5rem;color:#fff;position:relative;overflow:hidden}}
.hero-body{{position:relative;z-index:1;max-width:780px}}.hero-tag{{display:inline-block;background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.3);padding:.3rem 1.1rem;border-radius:50px;font-size:.82rem;font-weight:600;margin-bottom:1.2rem}}
.hero h1{{font-size:clamp(2.2rem,5vw,4rem);font-weight:800;margin-bottom:1.2rem;line-height:1.15;letter-spacing:-.02em}}.hero-sub{{font-size:1.1rem;opacity:.9;max-width:560px;margin:0 auto 2.2rem}}
.hero-btns{{display:flex;gap:1rem;justify-content:center;flex-wrap:wrap}}
.section{{padding:6rem 0}}.alt{{background:var(--alt)}}.container{{max-width:1180px;margin:0 auto;padding:0 5%}}
.label{{font-size:.72rem;font-weight:700;letter-spacing:.15em;color:var(--primary);text-transform:uppercase;margin-bottom:.6rem}}.label.center{{text-align:center}}
h2{{font-size:clamp(1.8rem,3vw,2.6rem);font-weight:800;letter-spacing:-.02em;margin-bottom:2.5rem}}h2.center{{text-align:center}}p{{color:var(--muted);margin-bottom:1rem;font-size:.98rem}}
.about-grid{{display:grid;grid-template-columns:1fr 1fr;gap:4rem;align-items:center}}.img-box{{width:100%;height:380px;background:linear-gradient(135deg,{color}22,{color}44);border-radius:var(--r);display:flex;align-items:center;justify-content:center;font-size:5rem;border:1px solid var(--border)}}
.service-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1.75rem}}
.card{{background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:2.25rem 1.75rem;box-shadow:var(--sh);transition:all var(--t);overflow:hidden}}
.card:hover{{transform:translateY(-8px);box-shadow:var(--shl);border-color:{color}44}}
.card-icon{{font-size:2.5rem;margin-bottom:1rem}}
.card h3{{font-size:1.15rem;font-weight:700;margin-bottom:.6rem}}
.card p{{margin:0;font-size:.93rem}}

/* Icon Card Special */
.icon-card.pulse-hover:hover .card-icon {{ transform: scale(1.1); transition: transform 0.3s ease; }}

/* Image Card */
.img-card{{padding:0}} .card-body{{padding:1.5rem}}
.img-card img{{transition: transform 0.5s ease;}} .img-card:hover img{{transform: scale(1.05);}}

/* Text List */
.service-list{{display:flex;flex-direction:column;gap:1.5rem;max-width:800px;margin:0 auto}}
.list-item{{padding:1.5rem;border-left:4px solid var(--primary);background:var(--bg);box-shadow:var(--sh);border-radius:0 var(--r) var(--r) 0;transition:all var(--t)}}
.list-item:hover{{transform:translateX(10px);background:var(--alt)}}

/* Slider */
.service-slider-wrap{{overflow:hidden;padding:2rem 0;position:relative}}
.slider-track{{display:flex;gap:1.75rem;width:max-content;animation: scrollArc 40s linear infinite}}
.slider-item{{width:300px;flex-shrink:0}}
@keyframes scrollArc {{ 0% {{ transform: translateX(0); }} 100% {{ transform: translateX(-50%); }} }}
.service-slider-wrap:hover .slider-track {{ animation-play-state: paused; }}

/* Hover V2 (Glow/Scale) */
.hover-card-v2:hover {{ background: var(--primary); color: #fff; transform: scale(1.05); }}
.hover-card-v2:hover p, .hover-card-v2:hover h3 {{ color: #fff; }}

/* Horizontal Scroll */
.service-scroll-container{{display:flex;gap:1.5rem;overflow-x:auto;padding:1rem 2rem;scrollbar-width:none; scroll-snap-type: x mandatory;}}
.service-scroll-container::-webkit-scrollbar {{ display:none }}
.scroll-card{{width:320px;flex-shrink:0; scroll-snap-align: start;}}

/* Generic Animations */
.slide-in{{opacity:0;transform:translateX(-50px);transition:all 0.8s ease-out}}
.slide-in.visible{{opacity:1;transform:translateX(0)}}
.gallery-grid{{display:grid;grid-template-columns:repeat(3,1fr);grid-template-rows:repeat(2,240px);gap:1rem}}
.gallery-item{{border-radius:var(--r);overflow:hidden;position:relative;cursor:pointer;transition:transform var(--t)}}.gallery-item:hover{{transform:scale(1.02)}}.gallery-item:hover .overlay{{opacity:1}}
.overlay{{position:absolute;inset:0;background:rgba(0,0,0,.65);display:flex;flex-direction:column;align-items:center;justify-content:center;opacity:0;transition:opacity var(--t);padding:1rem;text-align:center}}
.overlay span{{color:#fff;font-weight:700;font-size:1.2rem;margin-bottom:.3rem;display:block}}
.overlay p{{color:rgba(255,255,255,.8);font-size:.85rem;font-weight:600;text-transform:uppercase;letter-spacing:.05em;margin:0}}
  /* Testimonial Layouts */
  .testi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 2rem; }}
  .testi-card {{ background: var(--bg); border: 1px solid var(--border); border-radius: var(--r); padding: 2.25rem 1.75rem; box-shadow: var(--sh); transition: all var(--t); color: var(--text); }}
  .testi-card p, .testi-card strong {{ color: var(--text) !important; }}
  .testi-card span {{ color: var(--light) !important; opacity: 0.8; }}
  .pulse-hover:hover {{ transform: translateY(-10px); box-shadow: var(--shl); border-color: var(--primary); }}
  .scale-hover:hover {{ transform: scale(1.05); }}
  .glass-card {{ background: rgba(255,255,255,0.05); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.1); color: inherit; }}
  .glass-card:hover {{ border-color: var(--primary); background: rgba(255,255,255,0.1); }}
  
  .testi-parallax-section {{ background-image: linear-gradient(rgba(0,0,0,0.7), rgba(0,0,0,0.7)), url('https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=1600&q=80'); background-attachment: fixed; background-size: cover; color: white !important; }}
  .testi-parallax-section h2, .testi-parallax-section p, .testi-parallax-section cite, .testi-parallax-section strong {{ color: white !important; }}
  
  .testi-quotes-list {{ max-width: 900px; margin: 0 auto; text-align: center; }}
  .testi-quote-item {{ margin-bottom: 4rem; position: relative; }}
  .quote-icon {{ font-size: 5rem; color: var(--primary); opacity: 0.3; font-family: serif; line-height: 1; margin-bottom: -1rem; }}
  .testi-quote-item blockquote {{ font-family: var(--font-h); font-size: clamp(1.5rem, 3vw, 2.2rem); font-weight: 600; font-style: italic; margin-bottom: 1.5rem; line-height: 1.3; }}
  .testi-quote-item cite {{ font-style: normal; font-weight: 700; color: var(--muted); }}
  
  .testi-beside {{ display: flex; align-items: center; gap: 2rem; padding: 2rem; text-align: left; }}
  .testi-img {{ width: 120px; height: 120px; border-radius: 50%; overflow: hidden; flex-shrink: 0; border: 4px solid var(--primary-light); }}
  .testi-img img {{ width: 100%; height: 100%; object-fit: cover; }}
  .testi-content p {{ font-style: italic; font-size: 1.1rem; margin-bottom: 1rem; color: inherit; }}
  .testi-content strong {{ display: block; font-size: 1.1rem; }}
  .testi-content span {{ font-size: 0.85rem; opacity: 0.8; }}
  
  .testi-author {{ display: flex; align-items: center; gap: 0.85rem; margin-top: 1.5rem; }}
  .avatar {{ width: 44px; height: 44px; border-radius: 50%; background: linear-gradient(135deg, var(--primary), var(--dark)); color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.85rem; flex-shrink: 0; }}
  .avatar-round {{ width: 50px; height: 50px; border-radius: 50%; object-fit: cover; border: 2px solid var(--primary); }}
  
  /* Slider */
  .testi-slider-track {{ display: flex; gap: 2rem; animation: testiScroll 40s linear infinite; width: max-content; padding: 2rem 0; }}
  .testi-slider-track:hover {{ animation-play-state: paused; }}
  .testi-slide {{ width: 350px; flex-shrink: 0; }}
  @keyframes testiScroll {{ 0% {{ transform: translateX(0); }} 100% {{ transform: translateX(-50%); }} }}
.contact-wrap{{max-width:680px;margin:0 auto;background:var(--alt);border:1px solid var(--border);border-radius:var(--r);padding:3rem;box-shadow:var(--sh)}}
.contact-form{{display:flex;flex-direction:column;gap:1.1rem}}.field-row{{display:grid;grid-template-columns:1fr 1fr;gap:1.1rem}}
.field input,.field textarea{{width:100%;padding:.9rem 1rem;border:1.5px solid var(--border);border-radius:10px;font-family:inherit;font-size:.95rem;color:var(--text);background:var(--bg);transition:border-color var(--t),box-shadow var(--t)}}
.field input:focus,.field textarea:focus{{outline:none;border-color:var(--primary);box-shadow:0 0 0 3px {color}22}}.field textarea{{resize:vertical}}.contact-form .btn-primary{{width:100%;justify-content:center;padding:1rem}}
.footer{{background:#0f172a;color:#94a3b8;text-align:center;padding:4rem 0 2.5rem}}.footer-logo{{font-size:1.8rem;font-weight:800;color:#fff;margin-bottom:.75rem}}.copy{{font-size:.82rem;margin-top:1.5rem;color:#475569;margin-bottom:0}}
.fade-in{{opacity:0;transform:translateY(28px);transition:opacity .7s ease-out,transform .7s ease-out}}.fade-in.visible{{opacity:1;transform:none}}
@media(max-width:900px){{.about-grid{{grid-template-columns:1fr}}.gallery-grid{{grid-template-columns:repeat(2,1fr);grid-template-rows:repeat(3,200px)}}.field-row{{grid-template-columns:1fr}}}}
@media(max-width:640px){{.burger{{display:flex}}.nav-links{{position:absolute;top:100%;left:0;width:100%;background:rgba(255,255,255,.97);flex-direction:column;padding:1.5rem 5%;gap:1.25rem;clip-path:polygon(0 0,100% 0,100% 0,0 0);transition:clip-path .35s ease}}.nav-links.open{{clip-path:polygon(0 0,100% 0,100% 100%,0 100%);box-shadow:0 10px 20px rgba(0,0,0,.08)}}.gallery-grid{{grid-template-columns:1fr;grid-template-rows:none}}.gallery-item{{height:180px}}.contact-wrap{{padding:2rem 1.25rem}}}}
/* ── EDITING PANEL ────────────────────────────────────────── */
#editor-toggle{{position:fixed;bottom:2rem;right:2rem;z-index:10000;background:linear-gradient(135deg,#2563eb,#7c3aed);color:#fff;border:none;border-radius:50px;padding:.7rem 1.4rem;font-size:.9rem;font-weight:700;cursor:pointer;box-shadow:0 6px 20px rgba(37,99,235,.5);transition:all .3s;font-family:inherit}}
#editor-toggle:hover{{transform:translateY(-2px);box-shadow:0 10px 28px rgba(37,99,235,.6)}}
#editor-panel{{position:fixed;top:0;right:-340px;width:320px;height:100vh;background:#1e293b;border-left:1px solid #334155;z-index:9999;overflow-y:auto;transition:right .35s cubic-bezier(.4,0,.2,1);display:flex;flex-direction:column;padding:0}}
#editor-panel.open{{right:0}}
.ep-header{{display:flex;align-items:center;justify-content:space-between;padding:1rem 1.25rem;background:#0f172a;border-bottom:1px solid #334155;font-weight:700;color:#fff;font-size:.95rem;flex-shrink:0}}
#ep-close{{background:none;border:none;color:#94a3b8;font-size:1.2rem;cursor:pointer;line-height:1}}#ep-close:hover{{color:#fff}}
.ep-tabs{{display:flex;background:#0f172a;border-bottom:1px solid #334155;flex-shrink:0}}
.ep-tab{{flex:1;background:none;border:none;color:#64748b;font-family:inherit;font-size:.78rem;font-weight:600;padding:.65rem .2rem;cursor:pointer;border-bottom:2px solid transparent;transition:all .2s}}
.ep-tab.active{{color:#60a5fa;border-bottom-color:#60a5fa}}
.ep-pane{{display:none;flex-direction:column;gap:.6rem;padding:1rem 1.25rem;flex:1}}
.ep-pane.active{{display:flex}}
.ep-pane label{{font-size:.78rem;font-weight:600;color:#94a3b8;margin-top:.25rem}}
.ep-section-label{{font-size:.7rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#60a5fa;margin-top:.75rem;padding-top:.75rem;border-top:1px solid #334155}}
.ep-section-label:first-child{{margin-top:0;padding-top:0;border-top:none}}
.ep-input{{width:100%;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:8px;padding:.55rem .75rem;font-family:inherit;font-size:.85rem;transition:border-color .2s}}
.ep-input:focus{{outline:none;border-color:#2563eb}}
select.ep-input{{cursor:pointer}}
input[type="file"].ep-input{{padding:.4rem .5rem;color:#94a3b8}}
.ep-textarea{{resize:vertical;min-height:72px}}
.ep-toggle-row{{display:flex;align-items:center;gap:.5rem;color:#e2e8f0;font-size:.85rem;cursor:pointer;padding:.25rem 0}}
.ep-toggle-row input[type="checkbox"]{{accent-color:#2563eb;width:16px;height:16px;cursor:pointer}}
.ep-btn{{width:100%;background:#1e3a5f;border:1px solid #334155;color:#93c5fd;border-radius:8px;padding:.55rem .8rem;font-family:inherit;font-size:.82rem;font-weight:600;cursor:pointer;text-align:left;transition:all .2s;margin-top:.15rem}}
.ep-btn:hover{{background:#2563eb;color:#fff;border-color:#2563eb}}
.ep-btn-primary{{background:linear-gradient(135deg,#2563eb,#7c3aed)!important;color:#fff!important;border-color:transparent!important}}
.ep-btn-primary:hover{{opacity:.9;transform:translateY(-1px)}}
.ep-color-picker{{width:100%;height:44px;border:1px solid #334155;border-radius:8px;cursor:pointer;background:none;padding:2px}}
.ep-slider{{width:100%;accent-color:#2563eb}}
.ep-footer{{padding:1rem 1.25rem;border-top:1px solid #334155;flex-shrink:0}}
.ep-save{{width:100%;justify-content:center;text-align:center;padding:.75rem}}
.ep-toast{{position:absolute;bottom:5rem;left:50%;transform:translateX(-50%);background:#059669;color:#fff;padding:.5rem 1.2rem;border-radius:50px;font-size:.82rem;font-weight:600;white-space:nowrap;z-index:10001}}"""

    js = r"""const navbar=document.getElementById('navbar');
window.addEventListener('scroll',()=>navbar.classList.toggle('scrolled',window.scrollY>40),{passive:true});
const burger=document.getElementById('burger'),navLinks=document.getElementById('navLinks');
burger.addEventListener('click',()=>navLinks.classList.toggle('open'));
navLinks.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>navLinks.classList.remove('open')));
const obs=new IntersectionObserver((e)=>e.forEach(x=>{if(x.isIntersecting){x.target.classList.add('visible');obs.unobserve(x.target);}}),{threshold:0.12,rootMargin:'0px 0px -40px 0px'});
document.querySelectorAll('.fade-in, .slide-in').forEach(el=>obs.observe(el));
document.getElementById('cForm')?.addEventListener('submit',e=>{e.preventDefault();const b=e.target.querySelector('button[type="submit"]');b.textContent='✅ Message Sent!';b.disabled=true;setTimeout(()=>{b.textContent='Send Message';b.disabled=false;e.target.reset();},3000);});
/* ── EDITING PANEL ── */
const editorToggle=document.getElementById('editor-toggle');
const editorPanel=document.getElementById('editor-panel');
const epClose=document.getElementById('ep-close');
editorToggle.addEventListener('click',()=>editorPanel.classList.toggle('open'));
epClose.addEventListener('click',()=>editorPanel.classList.remove('open'));
// Tab switching
document.querySelectorAll('.ep-tab').forEach(tab=>{
  tab.addEventListener('click',()=>{
    document.querySelectorAll('.ep-tab').forEach(t=>t.classList.remove('active'));
    document.querySelectorAll('.ep-pane').forEach(p=>p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('ep-'+tab.dataset.tab)?.classList.add('active');
  });
});
// Live content editing helper
function liveEdit(id,val){const el=document.getElementById(id);if(el)el.textContent=val;}
// Section toggle
function toggleSection(id,show){const el=document.getElementById(id);if(el)el.style.display=show?'':'none';}
// Image preview & apply
const imgFileInput=document.getElementById('img-file-input');
imgFileInput?.addEventListener('change',function(){
  const file=this.files[0];if(!file)return;
  const reader=new FileReader();
  reader.onload=e=>{
    const pw=document.getElementById('img-preview-wrap');
    const pi=document.getElementById('img-preview');
    if(pw&&pi){pw.style.display='block';pi.src=e.target.result;}
  };
  reader.readAsDataURL(file);
});
function applyNewImage(){
  const section=document.getElementById('img-section-sel')?.value;
  const file=imgFileInput?.files[0];
  if(!file){alert('Please select an image first.');return;}
  const reader=new FileReader();
  reader.onload=e=>{
    const url=e.target.result;
    if(section==='hero'){
      const heroEl=document.getElementById('home');
      if(heroEl){heroEl.style.backgroundImage='url('+url+')';heroEl.style.backgroundSize='cover';heroEl.style.backgroundPosition='center';}
    }else if(section==='about'){
      const wrap=document.getElementById('about-img-wrap');
      if(wrap){wrap.innerHTML='<img src="'+url+'" alt="About" style="width:100%;height:380px;object-fit:cover;border-radius:14px;">';}
    }else if(section==='gallery'){
      const grid=document.getElementById('gallery-grid');
      if(grid){const item=document.createElement('div');item.className='gallery-item';item.style.cssText='background-image:url('+url+');background-size:cover;background-position:center;';item.innerHTML='<div class="overlay"><span>New Image</span></div>';grid.appendChild(item);}
    }else if(section==='contact'){
      const wrap=document.getElementById('contact');
      if(wrap){const banner=document.createElement('div');banner.style.cssText='margin-bottom:2rem;border-radius:14px;overflow:hidden;';banner.innerHTML='<img src="'+url+'" alt="Banner" style="width:100%;height:220px;object-fit:cover;">';const h2=wrap.querySelector('h2');if(h2)h2.after(banner);}
    }
  };
  reader.readAsDataURL(file);
}
// Theme color
function applyThemeColor(val){
  document.documentElement.style.setProperty('--primary',val);
  const r=parseInt(val.slice(1,3),16),g=parseInt(val.slice(3,5),16),b=parseInt(val.slice(5,7),16);
  const dark='#'+[r-30,g-30,b-30].map(x=>Math.max(0,x).toString(16).padStart(2,'0')).join('');
  document.documentElement.style.setProperty('--dark',dark);
}
// Font switcher
function applyFont(val){
  const fontName=val.replace(/\+/g,' ');
  const existing=document.getElementById('ep-font-link');
  if(existing)existing.remove();
  const link=document.createElement('link');
  link.id='ep-font-link';link.rel='stylesheet';
  link.href='https://fonts.googleapis.com/css2?family='+val+':wght@400;600;700;800&display=swap';
  document.head.appendChild(link);
  document.body.style.fontFamily="'"+fontName+"', sans-serif";
}
// Spacing slider
function applySpacing(val){
  document.getElementById('spacing-val').textContent=val+'rem';
  document.querySelectorAll('.section').forEach(s=>s.style.padding=val+'rem 0');
}
// Add new section
function addSection(type){
  const footer=document.getElementById('footer');
  if(!footer)return;
  const id='added-'+type+'-'+Date.now();
  const templates={
    testimonials:'<section id="'+id+'" class="section alt" style="padding:5rem 0;"><div class="container"><p class="label center">TESTIMONIALS</p><h2 class="center">More Client Reviews</h2><div class="testi-grid"><div class="testi-card"><p>\\"Amazing experience working with this team!\\"</p><div class="testi-author"><div class="avatar">CK</div><div><strong>Chris King</strong><span>Manager, Corp X</span></div></div></div></div></div></section>',
    pricing:'<section id="'+id+'" class="section" style="padding:5rem 0;"><div class="container"><p class="label center">PRICING</p><h2 class="center">Our Plans</h2><div class="service-grid"><div class="card"><div class="card-icon">💎</div><h3>Starter – $29/mo</h3><p>Perfect for small businesses and individuals.</p></div><div class="card"><div class="card-icon">🚀</div><h3>Pro – $79/mo</h3><p>Advanced features for growing teams.</p></div><div class="card"><div class="card-icon">🏢</div><h3>Enterprise – $199/mo</h3><p>Full-scale solution for large organisations.</p></div></div></div></section>',
    faq:'<section id="'+id+'" class="section alt" style="padding:5rem 0;"><div class="container"><p class="label center">FAQ</p><h2 class="center">Frequently Asked Questions</h2><div style="max-width:740px;margin:0 auto;display:flex;flex-direction:column;gap:1rem;"><details style="background:#fff;border:1px solid var(--border);border-radius:12px;padding:1.25rem;"><summary style="font-weight:700;cursor:pointer;">What services do you offer?</summary><p style="margin-top:.75rem;">We offer a full range of professional services tailored to your business needs.</p></details><details style="background:#fff;border:1px solid var(--border);border-radius:12px;padding:1.25rem;"><summary style="font-weight:700;cursor:pointer;">How long does a project take?</summary><p style="margin-top:.75rem;">Timelines vary, but most projects are completed within 4–8 weeks.</p></details><details style="background:#fff;border:1px solid var(--border);border-radius:12px;padding:1.25rem;"><summary style="font-weight:700;cursor:pointer;">Do you offer support after launch?</summary><p style="margin-top:.75rem;">Yes! We provide ongoing support and maintenance packages.</p></details></div></div></section>',
    blog:'<section id="'+id+'" class="section" style="padding:5rem 0;"><div class="container"><p class="label center">BLOG</p><h2 class="center">Latest Articles</h2><div class="service-grid"><div class="card"><div class="card-icon">📰</div><h3>How to Grow Your Business</h3><p>Practical tips and strategies to scale your business effectively.</p><a href="#" style="color:var(--primary);font-weight:700;font-size:.9rem;">Read More →</a></div><div class="card"><div class="card-icon">💡</div><h3>The Power of Innovation</h3><p>Why embracing new ideas is key to long-term success.</p><a href="#" style="color:var(--primary);font-weight:700;font-size:.9rem;">Read More →</a></div><div class="card"><div class="card-icon">🚀</div><h3>Marketing in 2026</h3><p>Digital marketing trends you need to know about this year.</p><a href="#" style="color:var(--primary);font-weight:700;font-size:.9rem;">Read More →</a></div></div></div></section>'
  };
  if(templates[type]){footer.insertAdjacentHTML('beforebegin',templates[type]);}
}
// Clone section
function cloneSection(id){
  const el=document.getElementById(id);if(!el)return;
  const clone=el.cloneNode(true);
  clone.id=id+'-clone-'+Date.now();
  el.parentNode.insertBefore(clone,el.nextSibling);
}
// Save changes
function saveChanges(){
  try{
    localStorage.setItem('ep-saved-html',document.body.innerHTML);
    const toast=document.getElementById('ep-toast');
    if(toast){toast.hidden=false;setTimeout(()=>toast.hidden=true,2500);}
  }catch(e){alert('Save failed: '+e.message);}
}"""

    return {"html": html, "css": css, "js": js}


# ─────────────────────────────────────────────────────────────
#  DESIGN PROFILE RESOLVER
# ─────────────────────────────────────────────────────────────
import random as _random
import hashlib as _hashlib

def resolve_design_profile(website_type: str, color_hint: str) -> dict:
    wt = (website_type or "").lower()
    if any(k in wt for k in ["gym","fitness","training","workout","bodybuilding","crossfit"]):
        style = "gym"
    elif any(k in wt for k in ["coffee","cafe","espresso","latte","bakery","roastery"]):
        style = "coffee"
    elif any(k in wt for k in ["restaurant","cafe","food","bakery","bar","bistro","kitchen","pizza","sushi"]):
        style = "restaurant"
    elif any(k in wt for k in ["portfolio","freelance","designer","artist","creative","photography","illustrator"]):
        style = "portfolio"
    elif any(k in wt for k in ["startup","saas","tech","software","app","ai","product","platform"]):
        style = "startup"
    elif any(k in wt for k in ["agency","marketing","seo","branding","advertising","digital","pr"]):
        style = "agency"
    elif any(k in wt for k in ["law","finance","accounting","insurance","consulting","corporate","bank","audit"]):
        style = "corporate"
    elif any(k in wt for k in ["beauty","spa","salon","wellness","yoga","fashion","cosmetic","skincare","nail"]):
        style = "beauty"
    elif any(k in wt for k in ["education","school","course","learning","academy","tutor","university","training"]):
        style = "education"
    elif any(k in wt for k in ["blog","magazine","news","journal","media","publishing"]):
        style = "blog"
    elif any(k in wt for k in ["ecommerce","shop","store","retail","marketplace","product"]):
        style = "ecommerce"
    else:
        style = "startup"

    seed = int(_hashlib.md5(website_type.encode()).hexdigest(), 16) % 1000
    rng  = _random.Random(seed)
    
    service_layouts = ["icon-cards", "image-cards", "text-list", "animated-slider", "hover-cards", "horizontal-scroll"]
    testi_layouts   = ["card-grid", "slider-carousel", "parallax-bg", "glass-cards", "quote-centered", "image-beside"]

    profiles = {
        "restaurant": {
            "palettes": [
                ("Warm & Rich",    "#c2410c", "warm reds, burnt orange, cream and parchment whites"),
                ("Bistro Classic", "#92400e", "warm amber, espresso brown, soft ivory"),
                ("Modern Diner",   "#0f172a", "dark charcoal with gold accents and warm white"),
            ],
            "fonts": [("Poppins","Cinzel"),("Cinzel","Poppins")],
            "hero_titles": [
                "Taste the Art of Fine Dining",
                "Delicious Moments Served Daily",
                "Flavor That Brings People Together",
                "Exceptional Culinary Experience",
                "The Heart of Good Food"
            ],
            "layouts": [
                "full-bleed cinematic hero with parallax food background and reservation CTA overlay",
                "split-screen hero with large food image right and bold serif text left",
                "video-style dark hero with diagonal divider and warm gradient overlay",
            ],
            "nav_style": [
                "transparent overlay navbar turning solid on scroll",
                "dark sticky navbar with centered logo",
                "minimal warm-toned top bar with reservation button on right",
            ],
            "sections": [
                ["Cinematic parallax hero with ambiance imagery + reservation CTA","Signature Dishes (6-card menu grid with prices & descriptions)","Chef Story with large portrait photo (split layout)","Ambiance Gallery (masonry photo grid)","Diner Reviews/Testimonials (3 review cards)","Reservation Form section","Opening Hours + Location footer"],
                ["Full-screen hero with mood overlay","Today's Specials (horizontal scroll cards)","Our Story section (split layout)","Menu categories with hover-reveal cards","Ambiance Gallery","Testimonials from happy diners","Contact + embedded map placeholder","Footer"],
            ],
            "about_paragraphs": [
                "Our restaurant is a culinary haven where tradition meets innovation. We source the freshest local ingredients to craft dishes that celebrate the art of fine dining, providing an unforgettable experience for every guest.",
                "From our handcrafted pasta to our signature desserts, every element of our menu is prepared with passion and precision. We believe that great food has the power to bring people together and create lasting memories."
            ],
            "about_img_query": "food,dining,restaurant",
            "effects": ["parallax background on hero","hover card lift with warm shadow","staggered fade-in on menu cards","smooth underline nav hover"],
            "hero_layouts": ["centered", "split-left", "minimal-bottom"],
            "hero_btn_styles": ["rounded", "outline", "pill"],
            "hero_img_queries": ["restaurant,fine-dining", "gourmet,food", "chef,cooking"],
            "gallery_items": [
                {"title": "Signature Pizza", "label": "Main Course", "img_query": "pizza"},
                {"title": "Italian Pasta", "label": "Entree", "img_query": "pasta"},
                {"title": "Fresh Salads", "label": "Healthy", "img_query": "salad"},
                {"title": "Chef Specials", "label": "Premium", "img_query": "gourmet,food"},
                {"title": "Decadent Desserts", "label": "Sweet", "img_query": "cake"},
                {"title": "Craft Drinks", "label": "Beverages", "img_query": "cocktail"}
            ],
            "testimonials": [
                {"quote": "The best Italian food I've had in years. Highly recommended!", "name": "Marco Rossi", "role": "Food Critic"},
                {"quote": "Amazing atmosphere and even better pasta. A must-visit.", "name": "Sarah Jenkins", "role": "Local Guide"},
                {"quote": "Authentic flavors and great service. We'll be back!", "name": "David Chen", "role": "Customer"}
            ]
        },
        "photography": {
            "palettes": [
                ("Minimal Dark",  "#18181b", "charcoal black, crisp white, subtle zinc grey"),
                ("Studio White",  "#ffffff", "pure white, charcoal black, soft grey accents"),
                ("Sepia Mood",    "#78350f", "warm sepia, cream, deep brown"),
            ],
            "fonts": [("Inter","Roboto"),("Playfair Display","Lato"),("Montserrat","Open Sans")],
            "hero_titles": [
                "Capturing Moments That Matter",
                "Professional Photography",
                "Every Story Told Through a Lens",
                "Visual Storytelling Excellence",
                "Timeless Memories Captured"
            ],
            "layouts": [
                "full-screen minimal hero with large artistic photo",
                "asymmetric display hero with overlapping camera imagery",
                "clean white studio-style hero with centered typography",
            ],
            "nav_style": [
                "minimal transparent top bar",
                "dark sticky navbar with centered logo",
                "thin bottom-fixed navigation",
            ],
            "sections": [
                ["Full-screen image hero with minimal text","Portfolio Gallery (masonry layout)","About the Photographer section","Client Projects masonry grid","Testimonials","Contact form","Footer"],
            ],
            "about_paragraphs": [
                "I am a professional photographer dedicated to capturing the raw beauty and authentic emotion of every moment. My work focuses on visual storytelling, blendid artistic vision with technical precision.",
                "With over a decade of experience in the field, I specialize in studio portraits and landscape photography, helping clients preserve their most precious memories in stunning detail."
            ],
            "about_img_query": "camera,photographer,studio",
            "effects": ["grayscale to color reveal on hover", "smooth image zoom on scroll", "minimalist text fade", "clean line animations"],
            "hero_layouts": ["split-right", "full-screen", "centered-floating"],
            "hero_btn_styles": ["outline", "rounded", "pill"],
            "hero_img_queries": ["photography,scene", "camera,lens", "landscape,portrait"],
            "gallery_items": [
                {"title": "Portrait Session", "label": "Studio", "img_query": "portrait"},
                {"title": "Wedding Magic", "label": "Events", "img_query": "wedding"},
                {"title": "Nature Escapes", "label": "Landscape", "img_query": "landscape"},
                {"title": "Urban Explorations", "label": "Street", "img_query": "urban,photography"},
                {"title": "Product Shoots", "label": "Commercial", "img_query": "product,photography"},
                {"title": "Abstract Art", "label": "Creative", "img_query": "abstract,art"}
            ],
            "testimonials": [
                {"quote": "Captured the essence of our wedding perfectly. Truly magical.", "name": "Jessica Moore", "role": "Bride"},
                {"quote": "Highly professional and an eye for the most unique shots.", "name": "Kevin White", "role": "Model"},
                {"quote": "The best portfolio work I have seen in years.", "name": "Linda Gray", "role": "Creative Director"}
            ]
        },
        "portfolio": {
            "palettes": [
                ("Dark Portfolio", "#6d28d9", "deep purple on near-black with electric violet accents"),
                ("Monochrome Bold","#18181b", "charcoal black, crisp white, subtle zinc grey"),
                ("Acid Green",     "#16a34a", "acid electric green on near-black with white text"),
            ],
            "fonts": [("Inter","Roboto"),("Roboto","Inter")],
            "hero_titles": [
                "Crafting Digital Experiences",
                "Turning Ideas Into Reality",
                "Creative Developer Portfolio",
                "Building the Next Generation Web",
                "Innovation Through Modern Design"
            ],
            "layouts": [
                "asymmetric bento-grid hero with overlapping layered elements",
                "enormous display type hero that fills the full viewport height",
                "dark full-screen hero with animated grain/noise texture",
            ],
            "nav_style": [
                "floating pill navbar centered at page top",
                "minimal left sidebar navigation on desktop",
                "transparent hamburger-only overlay navbar",
            ],
            "sections": [
                ["Full-screen hero with animated display headline + glowing CTA button","Selected Projects (bento masonry grid)","About / Philosophy (large text section)","Skills & Tools (animated icon + tag cloud)","Creative Process (numbered horizontal flow steps)","Testimonials (dark glassmorphism cards)","Contact section","Footer"],
                ["Hero with enormous background display name typography","Featured Work (horizontal scroll project cards)","About me — split layout with photo","Services offered (bold icon list)","Client Testimonials","Large 'Let's work together' CTA section","Contact form","Footer"],
            ],
            "about_paragraphs": [
                "We are a creative collective of designers and developers dedicated to turning bold ideas into seamless digital realities. Our portfolio showcases a diverse range of projects, from immersive web experiences to minimalist branding.",
                "Our approach combines strategic thinking with artistic flair, ensuring that every project not only looks stunning but also delivers exceptional performance and user engagement in the modern digital landscape."
            ],
            "about_img_query": "workspace,developer,designer",
            "effects": ["staggered text reveal animation","hover image distort and zoom","cursor-following gradient glow","magnetic button effect on CTAs"],
            "hero_layouts": ["centered", "bento-grid", "full-bleed"],
            "hero_btn_styles": ["pill", "glass", "rounded"],
            "hero_img_queries": ["developer,workspace", "abstract,tech", "designer,macbook"],
            "gallery_items": [
                {"title": "SaaS Dashboard", "label": "Product", "img_query": "saas,dashboard"},
                {"title": "Team Synergy", "label": "Culture", "img_query": "team,work"},
                {"title": "Growth Analytics", "label": "Results", "img_query": "analytics"},
                {"title": "Mobile App UI", "label": "Mobile", "img_query": "mobile,app"},
                {"title": "Global Impact", "label": "Mission", "img_query": "global,tech"},
                {"title": "Customer Success", "label": "Service", "img_query": "customer,support"}
            ],
            "testimonials": [
                {"quote": "A visionary designer who understands brand identity deeply.", "name": "Robert Brown", "role": "CEO, TechFlow"},
                {"quote": "Delivered a stunning portfolio that boosted my clients.", "name": "Alice Green", "role": "Freelance Artist"},
                {"quote": "Creative, efficient, and a joy to work with on any project.", "name": "James Wilson", "role": "Project Manager"}
            ]
        },
        "gym": {
            "palettes": [
                ("Vibrant Power",  "#e11d48", "bold crimson red, charcoal, graphite, clean white"),
                ("Thunder Steel",  "#2563eb", "electric blue, deep navy, steel grey, white"),
                ("Neon Force",     "#84cc16", "lime energy, obsidian black, dark slate, white"),
            ],
            "fonts": [("Bebas Neue","Montserrat"),("Montserrat","Bebas Neue")],
            "hero_titles": [
                "Train Hard. Stay Strong.",
                "Unleash Your Inner Power",
                "Transform Your Fitness Journey",
                "Peak Performance Hub",
                "Your Strength, Our Mission"
            ],
            "layouts": [
                "high-impact dark hero with motion-blurred workout background and bold overlay",
                "split hero with intense black & white workout photography and large display type",
                "modern minimalist hero with sharp edges and vibrant accent neon gradients",
            ],
            "nav_style": [
                "dark sticky navbar with bold branding",
                "transparent navbar with high-contrast text",
                "industrial-style fixed top bar with Join button",
            ],
            "sections": [
                ["Intense dark hero with bold value statement","Signature Programs (3-tier strength plan grid)","Expert Trainers (split layout with large photos)","Success Stories (testimonial slider)","Join the movement (contact form)","Footer"],
            ],
            "about_paragraphs": [
                "We are a modern fitness center dedicated to helping individuals achieve their health and strength goals. Our gym offers professional trainers, advanced workout equipment, and personalized training programs designed for every fitness level.",
                "Our mission is to inspire people to live healthier lifestyles by providing a motivating environment, expert guidance, and innovative fitness solutions for your transformation journey."
            ],
            "about_img_query": "gym,fitness,workout",
            "effects": ["sharp card shadow lift","text skew on hover","high-contrast vibrant hover glow","smooth section reveal on scroll"],
            "hero_layouts": ["split-left", "full-screen", "diagonal-cut"],
            "hero_btn_styles": ["square-bold", "pill", "rounded"],
            "hero_img_queries": ["gym,workout", "fitness,strength", "athlete,motivation"],
            "gallery_items": [
                {"title": "Strength Training", "label": "Power", "img_query": "weightlifting"},
                {"title": "Cardio Blast", "label": "Endurance", "img_query": "running"},
                {"title": "Bodybuilding", "label": "Muscle", "img_query": "bodybuilding"},
                {"title": "Yoga Sessions", "label": "Flexibility", "img_query": "yoga"},
                {"title": "HIIT Classes", "label": "Energy", "img_query": "hiit"},
                {"title": "Nutrition Coaching", "label": "Social", "img_query": "healthy,food"},
            ],
            "testimonials": [
                {"quote": "The trainers helped me achieve my fitness goals faster than I expected.", "name": "Rahul Sharma", "role": "Gym Member"},
                {"quote": "Great equipment and motivating atmosphere.", "name": "Priya Kapoor", "role": "Fitness Enthusiast"},
                {"quote": "A perfect place for anyone serious about fitness.", "name": "Arjun Patel", "role": "Athlete"}
            ]
        },
        "coffee": {
            "palettes": [
                ("Espresso Gold",  "#78350f", "deep roasted brown, gold accents, warm cream"),
                ("Morning Mist",   "#a8a29e", "soft charcoal, warm beige, ivory, hint of mocha"),
                ("Forest Roastery","#166534", "deep evergreen, wood brown, soft cream"),
            ],
            "fonts": [("Playfair Display","Lora"),("Lora","Playfair Display")],
            "hero_titles": [
                "Freshly Brewed Happiness",
                "Your Daily Coffee Escape",
                "Where Coffee Meets Comfort",
                "A Better Way to Start Your Day",
                "Artisanal Roasts, Perfectly Brewed"
            ],
            "layouts": [
                "cinematic soft-focus hero with elegant serif typography and warm overlay",
                "split layout with warm wooden textures and minimalist coffee art left",
                "cosy full-bleed hero with soft morning sunlight highlights",
            ],
            "nav_style": [
                "warm transparent navbar with elegant serif logo",
                "minimalist sticky bar with soft cream tones",
                "classic brand top bar with centered nav items",
            ],
            "sections": [
                ["Warm morning hero with artisanal branding","The Daily Roast (visual grid of coffee blends)","Our Story section with wooden textures","Reviews (elegant soft testimonial cards)","Visit us section with map placeholder","Footer"],
            ],
            "about_paragraphs": [
                "Our coffee shop is a cozy place where coffee lovers gather to enjoy freshly brewed beverages made from premium beans. We combine quality ingredients with a warm atmosphere to create the perfect coffee experience.",
                "We believe that great coffee brings people together, which is why we focus on delivering exceptional flavors and a relaxing space for every guest to unwind and recharge."
            ],
            "about_img_query": "coffee,cafe,barista",
            "effects": ["soft image fade-in","elegant serif reveal on scroll","warm shadow on hover cards","minimalist line-draw icon animations"],
            "hero_layouts": ["minimal-centered", "split-right", "full-bleed-warm"],
            "hero_btn_styles": ["rounded", "pill", "outline"],
            "hero_img_queries": ["coffee,cup", "cafe,interior", "barista,roastery"],
            "gallery_items": [
                {"title": "Signature Espresso", "label": "Roast", "img_query": "espresso"},
                {"title": "Fresh Croissants", "label": "Bakery", "img_query": "croissant"},
                {"title": "Latte Art", "label": "Craft", "img_query": "latte,art"},
                {"title": "Cozy Interior", "label": "Setting", "img_query": "cafe,interior"},
                {"title": "Roasting Process", "label": "Behind-scenes", "img_query": "roasting"},
                {"title": "Coffee Beans", "label": "Source", "img_query": "coffee,bean"},
            ],
            "testimonials": [
                {"quote": "The coffee here is rich, smooth, and perfectly brewed.", "name": "Emily Brown", "role": "Coffee Lover"},
                {"quote": "A cozy place with the best latte in town.", "name": "Daniel Smith", "role": "Cafe Visitor"},
                {"quote": "I love the atmosphere and fresh pastries.", "name": "Sophia Wilson", "role": "Food Blogger"}
            ]
        },
        "startup": {
            "palettes": [
                ("Electric Blue",   "#2563eb", "electric blue on white with light grey surfaces"),
                ("Dark SaaS",       "#0f172a", "dark slate with cyan and indigo glow accents"),
                ("Violet Gradient", "#7c3aed", "violet to indigo gradient on white backgrounds"),
            ],
            "fonts": [("Inter","Inter"),("Outfit","Outfit"),("Plus Jakarta Sans","DM Sans")],
            "hero_titles": [
                "Crafting Digital Experiences",
                "Turning Ideas Into Reality",
                "Creative Developer Portfolio",
                "Building the Next Generation Web",
                "Innovation Through Modern Design"
            ],
            "layouts": [
                "gradient hero with floating UI product mockup screenshot",
                "centred hero with animated badge + gradient headline + CTA pair",
                "split hero bold text left with animated illustration or graphic right",
            ],
            "nav_style": [
                "frosted-glass sticky navbar with coloured CTA button",
                "dark sticky navbar with gradient CTA button",
                "minimal clean navbar with coloured badge and links",
            ],
            "sections": [
                ["Hero with animated badge + gradient headline + floating product mockup","Social proof logos marquee bar","Product Features (alternating image + text rows)","How It Works (3-step numbered horizontal flow)","Pricing Cards (3 tiers with highlighted popular plan)","Customer Testimonials (3-column card grid)","FAQ accordion section","Final CTA gradient banner","Footer"],
                ["Gradient hero with animated stat counters","Core features icon grid","Product screenshot / demo section","Integration partner logos grid","Testimonials","Pricing table","Footer"],
            ],
            "about_paragraphs": [
                "We are a forward-thinking technology team focused on building scalable solutions for the digital age. Our platform leverages the latest innovations to streamline workflows and empower teams to achieve more in less time.",
                "With a deep commitment to user-centric design and technical excellence, we help our clients navigate the complex landscape of modern software and emerge as leaders in their industry."
            ],
            "about_img_query": "startup,office,tech",
            "effects": ["glassmorphism feature cards","gradient headline text effect","animated gradient blob background","card scale and glow on hover"],
            "hero_layouts": ["centered", "split-left", "minimal-bottom"],
            "hero_btn_styles": ["pill", "glass", "rounded"],
            "hero_img_queries": ["startup,tech", "software,office", "innovation,gradient"],
            "gallery_items": [
                {"title": "Cloud Matrix", "label": "Infrastructure", "img_query": "server,tech"},
                {"title": "Agile Workflow", "label": "Process", "img_query": "writing,notes"},
                {"title": "Team Synergy", "label": "Culture", "img_query": "team,office"},
                {"title": "Global Launch", "label": "Impact", "img_query": "rocket,launch"},
                {"title": "User Analytics", "label": "Insights", "img_query": "data,analytics"},
                {"title": "Design Sprint", "label": "Creative", "img_query": "macbook,designer"}
            ],
            "testimonials": [
                {"quote": "This platform transformed how our team works. Absolute game changer.", "name": "Alex Rivera", "role": "CTO, NextStream"},
                {"quote": "Intuitive, powerful, and scalable. Everything we needed.", "name": "Jordan Smith", "role": "Product Manager"},
                {"quote": "The ROI was immediate. Incredible tool for any startup.", "name": "Maria Garcia", "role": "Founder, Elevate AI"}
            ]
        },
        "agency": {
            "palettes": [
                ("High Contrast",  "#111827", "near-black with electric indigo accent and crisp white"),
                ("Bold Orange",    "#ea580c", "bold burnt orange, dark charcoal, clean white"),
                ("Electric Slate", "#0f172a", "dark slate, cool grey, vibrant indigo accent"),
            ],
            "fonts": [("Syne","Inter"),("DM Sans","Manrope"),("Bebas Neue","Inter")],
            "hero_titles": [
                "Crafting Digital Experiences",
                "Turning Ideas Into Reality",
                "Creative Developer Portfolio",
                "Building the Next Generation Web",
                "Innovation Through Modern Design"
            ],
            "layouts": [
                "dark cinematic full-screen hero with oversized agency statement headline",
                "bold agency hero with overlaid text on dark moody image",
                "two-column hero with scrolling client logos column on one side",
            ],
            "nav_style": [
                "dark sticky navbar with bold logo and coloured CTA",
                "transparent navbar that reveals solid on scroll",
                "minimal navbar with animated underline link hover effect",
            ],
            "sections": [
                ["Dramatic dark full-screen hero with agency statement","Scrolling client logos marquee","Services (3-4 bold dark feature cards)","Case Studies + Selected Work (large featured project cards)","Team section","Testimonials","Start a project CTA section","Footer"],
                ["Hero","Awards + animated stat counters","Services grid","Recent case studies","Team members grid","Contact section","Footer"],
            ],
            "about_paragraphs": [
                "As a full-service creative agency, we specialize in crafting immersive brand identities and high-impact digital marketing strategies. Our team of experts works closely with clients to tell their unique stories in a crowded marketplace.",
                "We believe in the power of bold ideas and fearless execution. From viral social campaigns to enterprise-grade web development, we deliver results that move the needle and define the future of branding."
            ],
            "about_img_query": "agency,studio,creative",
            "effects": ["text scramble animation on hero headline","scrolling logos marquee animation","3D card tilt on hover","dark glassmorphism case study cards"],
            "hero_layouts": ["split-right", "full-screen", "centered-floating"],
            "hero_btn_styles": ["rounded", "pill", "outline"],
            "hero_img_queries": ["agency,creative", "office,studio", "branding,design"],
            "gallery_items": [
                {"title": "Brand Revival", "label": "Identity", "img_query": "branding"},
                {"title": "Social Surge", "label": "Marketing", "img_query": "mobile,social"},
                {"title": "Pixel Perfect", "label": "UI/UX", "img_query": "website,design"},
                {"title": "Video Vibe", "label": "Motion", "img_query": "video,camera"},
                {"title": "Strategy First", "label": "Consulting", "img_query": "meeting,office"},
                {"title": "Future Focus", "label": "Innovation", "img_query": "abstract,light"}
            ],
            "testimonials": [
                {"quote": "They didn't just build a brand; they told our story beautifully.", "name": "Emily Watson", "role": "Marketing Director"},
                {"quote": "Professional, creative, and highly impactful results.", "name": "Chris Miller", "role": "Founder, Echo Media"},
                {"quote": "The most seamless creative process we've ever experienced.", "name": "Liam Ross", "role": "CEO, Vibe Digital"}
            ]
        },
        "corporate": {
            "palettes": [
                ("Navy Professional","#1e3a8a","deep professional navy, sky blue, clean white"),
                ("Slate Authority",  "#334155","cool dark slate, light grey, white accents"),
                ("Teal Executive",   "#0d9488","sophisticated teal, forest green, white"),
            ],
            "fonts": [("Roboto","Roboto"),("Source Sans 3","Source Serif 4"),("IBM Plex Sans","IBM Plex Serif")],
            "hero_titles": [
                "Crafting Digital Experiences",
                "Turning Ideas Into Reality",
                "Creative Developer Portfolio",
                "Building the Next Generation Web",
                "Innovation Through Modern Design"
            ],
            "layouts": [
                "clean centred hero with headline and inline data stats bar below",
                "split hero with bold headline left and professional imagery right",
                "minimal hero with trust-signal icon badges below CTA",
            ],
            "nav_style": [
                "clean white sticky navbar with logo + nav links + coloured CTA button",
                "professional thin top bar + secondary main navigation",
                "minimal sticky navbar with clean professional typography",
            ],
            "sections": [
                ["Hero with clear value proposition + animated stats bar","Client/partner logo trust bar","Core Services (3-column card grid)","Why choose us (alternating feature rows with icons)","Leadership Team profiles","Client Testimonials","Partners + Certifications section","Contact form","Footer"],
                ["Hero","Company overview + video CTA placeholder","Service lines grid","Case studies highlights","Team profiles","Testimonials","Contact form + location map placeholder","Footer"],
            ],
            "about_paragraphs": [
                "We are a professional consulting firm providing strategic guidance and operational excellence to global enterprises. Our team of experienced advisors helps leaders identify opportunities and mitigate risks in a rapidly changing world.",
                "Our approach is data-driven and results-oriented, ensuring that our partners maintain a competitive edge and achieve sustainable growth through informed decision-making and efficient resource management."
            ],
            "about_img_query": "corporate,office,business",
            "effects": ["counter animation for key stats","subtle fade-in scroll animations","professional box-shadow hover cards","clean underline nav hover"],
            "hero_layouts": ["split-left", "centered", "minimal"],
            "hero_btn_styles": ["rounded", "outline", "square-bold"],
            "hero_img_queries": ["corporate,office", "business,meeting", "skyscraper,city"],
            "gallery_items": [
                {"title": "Global Logistics", "label": "Operations", "img_query": "shipping,logistics"},
                {"title": "Financial Audit", "label": "Compliance", "img_query": "finance,calculator"},
                {"title": "Strategic Summit", "label": "Leadership", "img_query": "conference,room"},
                {"title": "Tech Integration", "label": "Infrastructure", "img_query": "tech,business"},
                {"title": "Client Success", "label": "Consulting", "img_query": "handshake"},
                {"title": "New Horizons", "label": "Expansion", "img_query": "architecture"}
            ],
            "testimonials": [
                {"quote": "Exceptional service and strategic insights that drove our growth.", "name": "John Anderson", "role": "CEO, Sterling Corp"},
                {"quote": "A reliable partner for all our corporate needs.", "name": "Karen Thompson", "role": "Managing Director"},
                {"quote": "Their professionalism and expertise are unmatched in the industry.", "name": "Michael Chen", "role": "Partner, Global Law"}
            ]
        },
        "beauty": {
            "palettes": [
                ("Blush Luxe",    "#f43f5e","rose pink, blush, soft white, cream"),
                ("Mauve Elegance","#a855f7","light purple, lavender, pearl white"),
                ("Champagne Gold","#d97706","warm champagne gold, ivory, soft peach"),
            ],
            "fonts": [("Cormorant Garamond","Raleway"),("Josefin Sans","Lato"),("Playfair Display","Montserrat")],
            "hero_titles": [
                "Crafting Digital Experiences",
                "Turning Ideas Into Reality",
                "Creative Developer Portfolio",
                "Building the Next Generation Web",
                "Innovation Through Modern Design"
            ],
            "layouts": [
                "dreamy soft-gradient hero with elegant centred serif typography",
                "split hero with large mood treatment image left and serif text right",
                "full-bleed mood photo hero with translucent frosted glass overlay",
            ],
            "nav_style": [
                "minimal light navbar with centered serif logo",
                "transparent elegant navbar with cursive logo",
                "pastel-tinted sticky top bar",
            ],
            "sections": [
                ["Elegant mood hero with soft gradients","Signature Treatments (soft card grid with icons)","Brand philosophy quote section","Before & After gallery grid","Client reviews (soft rounded testimonial cards)","Book a session CTA section","Footer"],
                ["Hero with soft mood imagery","Our approach / philosophy long text section","Service menu (list with icons + prices)","Gallery of work","Testimonials","Contact & booking form","Footer"],
            ],
            "about_paragraphs": [
                "Our wellness sanctuary is dedicated to restoring balance and enhancing natural beauty. We offer a curated selection of premium spa treatments and skincare solutions designed to rejuvenate both body and spirit in a tranquil environment.",
                "We believe that self-care is a journey, not a destination. Our expert therapists are committed to providing personalized care that leaves you feeling refreshed, confident, and profoundly relaxed."
            ],
            "about_img_query": "spa,wellness,beauty",
            "effects": ["soft blur glassmorphism cards","pastel gradient backgrounds per section","fade opacity reveal on hover","floating botanical illustration accent"],
            "hero_layouts": ["centered", "split-right", "full-bleed-warm"],
            "hero_btn_styles": ["pill", "rounded", "outline"],
            "hero_img_queries": ["spa,beauty", "wellness,relax", "flowers,minimal"],
            "gallery_items": [
                {"title": "Floral Facial", "label": "Skincare", "img_query": "facial"},
                {"title": "Stone Massage", "label": "Therapy", "img_query": "massage,stone"},
                {"title": "Zen Garden", "label": "Ambiance", "img_query": "zen,garden"},
                {"title": "Organic Glow", "label": "Beauty", "img_query": "skincare,product"},
                {"title": "Quiet Moments", "label": "Wellness", "img_query": "relaxing"},
                {"title": "Pure Bliss", "label": "Luxury", "img_query": "spa,interior"}
            ],
            "testimonials": [
                {"quote": "An absolute sanctuary. I left feeling completely reborn.", "name": "Sophia Bennett", "role": "Frequent Guest"},
                {"quote": "The attention to detail and care is simply wonderful.", "name": "Isabella Thorne", "role": "Lifestyle Blogger"},
                {"quote": "Best facial I've ever had. My skin has never looked better.", "name": "Chloe Evans", "role": "Customer"}
            ]
        },
        "education": {
            "palettes": [
                ("Sky Blue Learn","#2563eb","bright friendly blue, sky blue, clean white"),
                ("Emerald Study", "#059669","fresh green, mint, clean white"),
                ("Warm Academy",  "#d97706","warm amber, light cream, white"),
            ],
            "fonts": [("Nunito","Open Sans"),("Poppins","Inter"),("Quicksand","Rubik")],
            "hero_titles": [
                "Crafting Digital Experiences",
                "Turning Ideas Into Reality",
                "Creative Developer Portfolio",
                "Building the Next Generation Web",
                "Innovation Through Modern Design"
            ],
            "layouts": [
                "friendly rounded hero with illustrated character or device mockup",
                "hero with prominent enrolment statistics counter",
                "split hero with course preview screenshot or video thumbnail",
            ],
            "nav_style": [
                "clean rounded white sticky navbar",
                "coloured brand top bar with main nav below",
                "minimal navbar with prominent enrol CTA button",
            ],
            "sections": [
                ["Hero with enrolment CTA + animated key stats","Featured Courses (3-4 card grid)","How It Works (3-step illustrated horizontal flow)","Why choose us (icon + text feature list)","Instructor profiles","Student testimonials","Pricing plans","FAQ accordion","Newsletter CTA","Footer"],
                ["Hero","Popular courses grid","About the academy + mission","Key learning outcomes","Student testimonials","Contact + enquiry form","Footer"],
            ],
            "about_paragraphs": [
                "We are a modern learning academy committed to empowering the next generation of leaders. Our comprehensive curriculum and expert instructors provide students with the tools they need to master new skills and excel in their careers.",
                "Our mission is to make high-quality education accessible to everyone. We foster a supportive community where curiosity is encouraged and lifelong learning is celebrated through innovative teaching methods and practical experience."
            ],
            "about_img_query": "education,school,learning",
            "effects": ["pop-in card hover with shadow lift","animated progress bars in stats","smooth x-accordion FAQ","confetti burst on CTA hover"],
            "hero_layouts": ["split-left", "full-screen", "centered-minimal"],
            "hero_btn_styles": ["rounded", "pill", "square-bold"],
            "hero_img_queries": ["education,learning", "classroom,study", "library,books"],
            "gallery_items": [
                {"title": "Future Leaders", "label": "Graduation", "img_query": "graduation"},
                {"title": "STEM Lab", "label": "Innovation", "img_query": "science,lab"},
                {"title": "Art Studio", "label": "Creative", "img_query": "painting"},
                {"title": "Campus Life", "label": "Community", "img_query": "campus"},
                {"title": "Coding Camp", "label": "Technology", "img_query": "coding"},
                {"title": "Quiet Study", "label": "Focus", "img_query": "reading,library"}
            ],
            "testimonials": [
                {"quote": "The curriculum is challenging but incredibly rewarding.", "name": "Noah Parker", "role": "Student"},
                {"quote": "Incredible instructors who truly care about our success.", "name": "Emma Wright", "role": "Alumni"},
                {"quote": "A supportive environment that fosters growth and curiosity.", "name": "Liam Scott", "role": "Parent"}
            ]
        },
        "blog": {
            "palettes": [
                ("Editorial Dark","#18181b","dark charcoal, near-black, crisp white"),
                ("Warm Ink",      "#292524","warm dark brown, cream text, sepia accent"),
                ("Clean Minimal", "#2563eb","minimal blue accent on white with dark body text"),
            ],
            "fonts": [("Playfair Display","Lato"),("Libre Baskerville","Source Sans 3"),("Merriweather","Inter")],
            "hero_titles": [
                "Crafting Digital Experiences",
                "Turning Ideas Into Reality",
                "Creative Developer Portfolio",
                "Building the Next Generation Web",
                "Innovation Through Modern Design"
            ],
            "layouts": [
                "magazine full-bleed hero with featured article image overlay",
                "editorial hero with large serif title and author byline",
                "minimal clean hero with category pills and search input",
            ],
            "nav_style": [
                "editorial top bar with category navigation row below",
                "minimal centred logo navbar",
                "clean sticky navbar with search icon and hamburger",
            ],
            "sections": [
                ["Magazine featured article hero","Latest posts (3-column editorial card grid)","Topics + Category browser pills","Featured long-read (large horizontal card)","Newsletter signup section","About the author","Footer"],
                ["Hero article","Recent posts grid","Popular topics list","Newsletter CTA banner","Footer"],
            ],
            "about_paragraphs": [
                "Welcome to our editorial space, where we share deep insights and fresh perspectives on the world around us. Our blog covers everything from lifestyle and culture to tech trends and expert advice, all curated for curious minds.",
                "We believe in the power of storytelling and information sharing. Our goal is to create a vibrant community of readers who engage with quality journalism and thought-provoking articles that challenge and inspire."
            ],
            "about_img_query": "blog,journal,writing",
            "effects": ["reading progress bar at page top","hover image reveal cards","smooth scroll with highlighted anchors","animated category pill hover"],
            "hero_layouts": ["full-screen", "split-right", "minimal-centered"],
            "hero_btn_styles": ["outline", "rounded", "pill"],
            "hero_img_queries": ["blog,writing", "journal,desk", "nature,aesthetic"],
            "gallery_items": [
                {"title": "Urban Stories", "label": "Lifestyle", "img_query": "city,life"},
                {"title": "Taste Travel", "label": "Food", "img_query": "food,travel"},
                {"title": "Tech Trends", "label": "Gadgets", "img_query": "gadget,tech"},
                {"title": "Mountain Muse", "label": "Outdoor", "img_query": "mountain"},
                {"title": "Mindful Living", "label": "Wellness", "img_query": "meditation"},
                {"title": "Digital Nomad", "label": "Work", "img_query": "laptop,beach"}
            ],
            "testimonials": [
                {"quote": "I love the clean layout and the quality of the articles.", "name": "Ava Johnson", "role": "Subscriber"},
                {"quote": "Finally a blog that focuses on meaningful storytelling.", "name": "Lucas Grey", "role": "Reader"},
                {"quote": "The best resource for travel and tech insights.", "name": "Mia Wong", "role": "Traveler"}
            ]
        },
        "ecommerce": {
            "palettes": [
                ("Luxury Dark",  "#0f172a","dark professional, high-contrast white, gold accent"),
                ("Minimal Mono", "#18181b","monochrome black and zinc, luxury minimal"),
                ("Bold Commerce","#dc2626","energetic red, dark background, clean white"),
            ],
            "fonts": [("Inter","Inter"),("Outfit","Outfit"),("DM Sans","DM Serif Display")],
            "hero_titles": [
                "Crafting Digital Experiences",
                "Turning Ideas Into Reality",
                "Creative Developer Portfolio",
                "Building the Next Generation Web",
                "Innovation Through Modern Design"
            ],
            "layouts": [
                "full-bleed promotional hero with overlaid offer badge and CTA",
                "split hero bold headline text left + product hero image right",
                "centred product hero with animated discount badge and countdown",
            ],
            "nav_style": [
                "e-commerce dark navbar with cart and search icons",
                "minimal clean store top navbar",
                "sticky navbar with categories mega-dropdown",
            ],
            "sections": [
                ["Promotional hero banner with animated offer badge","Featured product categories (visual icon grid)","Best Sellers (product card grid with rating + price)","Sale + Limited offer section","Brand Story section","Customer reviews grid","Newsletter signup with discount code","Footer"],
                ["Hero","New arrivals card grid","Shop by category visual tiles","Trending products grid","Brand guarantee icons bar","Testimonials","Footer"],
            ],
            "about_paragraphs": [
                "Our marketplace is built on a passion for quality and a commitment to exceptional service. We curate the best products from around the world, ensuring that our customers always find exactly what they need at the best prices.",
                "We believe that shopping should be a seamless and enjoyable experience. Our team works tirelessly to provide a secure platform, fast shipping, and world-class support for every customer who walks through our digital doors."
            ],
            "about_img_query": "shopping,store,product",
            "effects": ["product card zoom and shadow on hover","animated badge on featured items","sticky offer announcement bar on scroll","marquee scrolling offer text"],
            "hero_layouts": ["split-left", "full-bleed-warm", "centered"],
            "hero_btn_styles": ["square-bold", "pill", "rounded"],
            "hero_img_queries": ["shopping,fashion", "product,display", "store,interior"],
            "gallery_items": [
                {"title": "Latest Collection", "label": "Fashion", "img_query": "clothing"},
                {"title": "Winter Sale", "label": "Promotions", "img_query": "sale"},
                {"title": "Daily Essentials", "label": "Lifestyle", "img_query": "product,minimal"},
                {"title": "Tech Gear", "label": "Electronics", "img_query": "tech,gadget"},
                {"title": "Home Decor", "label": "Interior", "img_query": "home,decor"},
                {"title": "Summer Vibes", "label": "seasonal", "img_query": "summer,fashion"}
            ],
            "testimonials": [
                {"quote": "Fast shipping and the quality exceeded my expectations.", "name": "Olivia Rose", "role": "Verified Buyer"},
                {"quote": "The easiest shopping experience I've had online.", "name": "Ethan Hunt", "role": "Regular Customer"},
                {"quote": "Highly recommend this store for unique find and great service.", "name": "Grace Lee", "role": "Premium Member"}
            ]
        },
    }

    p = profiles[style]
    palette  = rng.choice(p["palettes"])
    fonts    = rng.choice(p["fonts"])
    layout   = rng.choice(p["layouts"])
    nav      = rng.choice(p["nav_style"])
    sections = rng.choice(p["sections"])
    effects  = rng.sample(p["effects"], min(3, len(p["effects"])))
    primary   = color_hint if (color_hint and color_hint not in ("#2563eb", "", "none")) else palette[1]
    title     = rng.choice(p.get("hero_titles", ["Modern Website Experience", "Building the Future", "Excellence in Every Pixel"]))
    about_p   = rng.sample(p.get("about_paragraphs", ["We are experts."]), min(len(p.get("about_paragraphs", [])), rng.randint(2,3)))
    about_iq  = p.get("about_img_query", "business,modern")
    about_l   = rng.choice(["image-left", "image-right", "centered"])
    
    # New Hero Tokens
    h_layout  = rng.choice(p.get("hero_layouts", ["centered", "split"]))
    h_fonts   = rng.choice(p.get("fonts", [("Inter", "Inter")]))
    h_btn_s   = rng.choice(p.get("hero_btn_styles", ["rounded", "pill"]))
    h_img_q   = rng.choice(p.get("hero_img_queries", ["modern,business"]))
    g_items   = p.get("gallery_items", [])
    t_items   = p.get("testimonials", [])
    s_layout  = p.get("service_layout", _random.choice(service_layouts))
    t_layout  = p.get("testi_layout", rng.choice(testi_layouts))

    return {
        "style":         style,
        "palette_name":  palette[0],
        "primary":       primary,
        "palette_desc":  palette[2],
        "font_heading":  h_fonts[0],
        "font_body":     h_fonts[1],
        "layout":        layout,
        "nav_style":     nav,
        "sections":      sections,
        "effects":       effects,
        "hero_title":    title,
        "about_p":       about_p,
        "about_iq":      about_iq,
        "hero_layout":   h_layout,
        "hero_btn_style": h_btn_s,
        "hero_img_query": h_img_q,
        "gallery_items": g_items,
        "testimonials":  t_items,
        "about_layout":  about_l,
        "service_layout": s_layout,
        "testi_layout":  t_layout
    }


# ─────────────────────────────────────────────────────────────
#  PROMPT BUILDER
# ─────────────────────────────────────────────────────────────
def build_prompt(data: dict) -> str:
    prompt_desc = data.get('description', '')
    return (
        "You are an expert website designer.\n\n"
        "Generate a modern responsive website based on the user's prompt.\n\n"
        "### IMPORTANT RULES\n"
        "1. Detect the website topic automatically from the prompt.\n"
        "2. Generate a UNIQUE hero section title that matches the topic. Be creative and evocative.\n"
        "3. NEVER use generic patterns like: 'Exceptional [Topic] Services', 'Welcome to [Company]', 'Professional [Topic] Solutions'.\n"
        "4. Specifically FORBIDDEN titles (Never use): 'Exceptional Services', 'Welcome to our website', 'Exceptional Gym Services', 'Exceptional Resturant Services', 'Exceptional Restaurant Services'.\n"
        "5. The hero title must reflect the industry specifically and emotionally.\n\n"
        "### INDUSTRY EXAMPLES\n"
        "• Gym → 'Train Hard. Stay Strong.', 'Unleash Your Inner Power', 'Transform Your Fitness Journey'\n"
        "• Coffee Shop → 'Freshly Brewed Happiness', 'Your Daily Coffee Escape', 'Where Coffee Meets Comfort'\n"
        "• Restaurant → 'Taste the Art of Fine Dining', 'Delicious Moments Served Daily', 'Flavor That Brings People Together'\n"
        "• Portfolio → 'Crafting Digital Experiences', 'Turning Ideas Into Reality', 'Creative Developer Portfolio'\n\n"
        "### FONT AND STYLE RULES\n"
        "Use appropriate Google Fonts based on the detected topic:\n"
        "• Gym/Fitness: Bebas Neue, Montserrat\n"
        "• Coffee Shop/Cafe: Playfair Display, Lora\n"
        "• Restaurant: Poppins, Cinzel\n"
        "• Portfolio/Modern: Inter, Roboto\n"
        'Always include: <link href="https://fonts.googleapis.com/css2?family=FONT_NAME&display=swap" rel="stylesheet">\n\n'
        "### LAYOUT & DESIGN RULES\n"
        "• Sections: HERO, ABOUT, SERVICES, CONTACT.\n"
        "• Hero Section MUST include: unique dynamic title, subtitle related to the prompt, TWO call-to-action buttons, gradient background, and a responsive layout.\n"
        "• Services Section: Generate exactly 6 unique services relevant to the topic with matching icons.\n"
        "• Each generation MUST produce: different hero titles, different fonts, different layouts, and unique color palettes.\n\n"
        "### OUTPUT FORMAT\n"
        "Return ONLY valid JSON. Do not include explanations.\n"
        "{\n"
        '  "html": "<!-- complete valid HTML code here -->",\n'
        '  "css": "/* complete CSS with modern effects here */",\n'
        '  "js": "/* interactive JS features here */"\n'
        "}\n\n"
        f"User Prompt: {prompt_desc}\n"
    )


# ─────────────────────────────────────────────────────────────
#  AI RESPONSE CLEANER
# ─────────────────────────────────────────────────────────────
def clean_response(raw: str) -> dict:
    system_msg = """You are an Expert AI Website Designer. Your task is to generate a complete, responsive website based on a user prompt.
RULES:
- HERO SECTION: Must ADAPT COMPLETELY to the prompt. VARY the layout (centered, split, minimal), title style, and button styles.
- OUR WORK (Gallery): Generate 6 unique project items with TOPIC-SPECIFIC TITLES AND LABELS. Never use "Project Alpha", "Project Beta", etc.
- TESTIMONIALS: Generate 3 unique, realistic customer reviews related to the topic. Do NOT use generic names like "Jane Doe" or "Mark Smith". Include a name and a role/description.
- ABOUT SECTION:
    1. The ABOUT US section must choose ONE of these layouts: Image Left, Image Right, or Centered (no image). Ensure visual variety.
    2. Write 2-3 meaningful paragraphs for the 'About Us' description that are highly relevant to the website topic. Avoid generic fluff.
    3. If the layout includes an image, use an Unsplash image related to the prompt topic (e.g., /?gym, /?coffee).
- DYNAMIC ADAPTATION: Detect the business type and choose appropriate fonts (e.g., Gym=Bebas Neue, Coffee=Playfair Display).
- NO GENERIC TITLES: Do not use "Exceptional Services" or "Welcome to our website".
- IMAGERY: Use relevant Unsplash images (1600x900 for Hero).
- RESPONSIVE: Ensure the layout works on all screen sizes.
- OUTPUT: Return ONLY a valid JSON object with "html", "css", and "javascript" keys."""
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            result = json.loads(match.group())
        else:
            raise ValueError("AI returned invalid JSON. Try again.")
    # Normalise 'javascript' key → 'js' so the rest of the app works unchanged
    if "javascript" in result and "js" not in result:
        result["js"] = result.pop("javascript")
    return result


# ─────────────────────────────────────────────────────────────
#  GEMINI GENERATOR
# ─────────────────────────────────────────────────────────────
def gemini_generator(data: dict) -> dict:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash")
    prompt_text = build_prompt(data)
    print("\n[DEBUG] Sending Prompt to Gemini... (length:", len(prompt_text), ")")
    
    try:
        response = model.generate_content(
            prompt_text,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=8192,
            ),
        )
        print("\n[DEBUG] Gemini responded successfully. Parsing JSON...")
        # print("[DEBUG] RAW TEXT PREVIEW:", response.text[:200]) # Optional
        return clean_response(response.text)
    except Exception as e:
        print(f"\n[CRITICAL ERROR] Gemini generation exploded: {str(e)}")
        import traceback
        traceback.print_exc()
        raise e


# ─────────────────────────────────────────────────────────────
#  OPENAI GENERATOR
# ─────────────────────────────────────────────────────────────
def openai_generator(data: dict) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_KEY)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "- ABOUT SECTION: Generate 2-3 unique, meaningful paragraphs. DO NOT use generic phrases like \"We are a dedicated team\" or \"Our mission is to exceed expectations\".\n- IMAGE QUALITY: All <img> tags must have a relevant 'src' from Unsplash using the format: https://images.unsplash.com/photo-[ID]?auto=format&fit=crop&w=800&q=80 (use high-quality IDs) or a reliable placeholder like https://loremflickr.com/800/600/[topic].\n- About image must match the prompt topic perfectly.\n- Final JSON must contain: \"html\", \"css\", \"js\", \"name\", \"btype\".\nRespond only with valid JSON containing html, css, javascript keys. No markdown. No explanation."},
            {"role": "user",   "content": build_prompt(data)},
        ],
        temperature=0.7,
        max_tokens=8192,
    )
    return clean_response(response.choices[0].message.content)


# ─────────────────────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────────────────────
@app.route("/")
def index():
    if has_gemini():
        engine = "Gemini AI (Free)"
    elif has_openai():
        engine = "OpenAI GPT-4o"
    else:
        engine = "Built-in Template"
    return render_template("index.html", engine=engine)


@app.route("/upload", methods=["POST"])
def upload_image():
    """Accept a single image file and return its public URL."""
    try:
        if "image" not in request.files:
            return jsonify({"error": "No file provided."}), 400
        file = request.files["image"]
        if file.filename == "":
            return jsonify({"error": "Empty filename."}), 400
        if not allowed_file(file.filename):
            return jsonify({"error": "File type not allowed. Use PNG, JPG, GIF, WEBP, or SVG."}), 400

        ext      = file.filename.rsplit(".", 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        save_path = UPLOAD_FOLDER / filename
        file.save(str(save_path))

        url = f"/static/uploads/{filename}"
        return jsonify({"url": url})
    except Exception as e:
        print(f"[UPLOAD ERROR] {traceback.format_exc()}")
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500


@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"error": "No data received. Please fill the form."}), 400

        # ── Choose generator ──────────────────────────────────
        website = None
        last_error = None

        if has_gemini():
            try:
                website = gemini_generator(data)
            except Exception as e:
                last_error = f"Gemini error: {str(e)}"
                print(f"[GEMINI ERROR] {last_error}\n{traceback.format_exc()}")
                # Fall through to template generator

        if website is None and has_openai():
            try:
                website = openai_generator(data)
            except Exception as e:
                last_error = f"OpenAI error: {str(e)}"
                print(f"[OPENAI ERROR] {last_error}\n{traceback.format_exc()}")

        if website is None:
            # Always fall back to template generator
            print(f"[INFO] Using template generator. Last AI error: {last_error}")
            website = template_generator(data)

        # ── Validate keys ─────────────────────────────────────
        for key in ("html", "css", "js"):
            if key not in website:
                raise ValueError(f"Missing key '{key}' in generated website.")

        # ── Saftey net for Dynamic View ───────────────────────
        user_desc = data.get("description", "").lower()
        dynamic_keywords = ["dynamic", "unique", "wild", "crazy", "experimental", "insane", "radical", "different", "futuristic", "out of the box", "insanely", "animated", "interactive", "modern", "immersive", "motion", "vibrant"]
        if any(kw in user_desc for kw in dynamic_keywords):
            website["view_type"] = "fullscreen"

        # Store on server side — cookie only holds a small UUID
        site_id = str(uuid.uuid4())
        WEBSITE_STORE[site_id] = website
        session["site_id"] = site_id

        return jsonify({"success": True})

    except Exception as e:
        print(f"[GENERATE ERROR] {traceback.format_exc()}")
        return jsonify({"error": f"Generation failed: {str(e)}"}), 500


@app.route("/preview")
def preview():
    site_id = session.get("site_id", "")
    website = WEBSITE_STORE.get(site_id, {})
    html = website.get("html", "")
    css  = website.get("css",  "")
    js   = website.get("js",   "")
    view_type = website.get("view_type", "editor")

    if not html:
        return render_template("index.html", engine="Built-in Template")
        
    if view_type == "fullscreen":
        return render_template("pure_view.html", website_html=html, website_css=css, website_js=js)
    else:
        return render_template("preview.html", website_html=html, website_css=css, website_js=js)


if __name__ == "__main__":
    # Use threaded=True so long AI requests don't block other requests
    app.run(debug=True, port=5000, threaded=True)
