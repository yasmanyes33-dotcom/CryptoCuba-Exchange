import os
import uuid
import sqlite3
import logging
import time
from datetime import datetime
from contextlib import closing

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler,
)
from telegram.constants import ParseMode

# ============================================================
# CONFIGURACIÓN
# ============================================================
WALLET_USDT = "0xAf6f75dB9B57A545E90Cc35B99200C7651Bd2054"
EXPLORER_BASE = "https://bscscan.com/address/"
NETWORK_NAME = "BEP20 · Binance Smart Chain"
DB_FILE = "bookings.db"
BOT_VERSION = "v7-BEP20-MULTI"

MAX_PEOPLE = 30
COOLDOWN_SECONDS = 3

TOURS = {
    "mountains": {
        "name_es": "A caballo a las Montañas",
        "name_en": "Horseback to the Mountains",
        "price": 10,
        "type": "per-person",
        "deposit": 50,
        "emoji": "🐎",
    },
    "valley": {
        "name_es": "A caballo — Valle de los Ingenios",
        "name_en": "Horseback — Valley of the Mills",
        "price": 20,
        "type": "per-person",
        "deposit": 50,
        "emoji": "🌾",
    },
    "city": {
        "name_es": "Carretón — Ciudad",
        "name_en": "Carretón — City Tour",
        "price": 20,
        "type": "rental",
        "deposit": 25,
        "emoji": "🐴",
    },
    "sunset": {
        "name_es": "Carretón — Atardecer",
        "name_en": "Carretón — Sunset Ride",
        "price": 40,
        "type": "rental",
        "deposit": 25,
        "emoji": "🌅",
    },
}

(TOUR, ADULTS, KIDS, DATE, NAME, NOTES, CONFIRM) = range(7)

# ============================================================
# TEXTOS MULTI-IDIOMA
# ============================================================
TEXTS = {
    "es": {
        "welcome": (
            "🐎 <b>¡Bienvenido a Trinidad Rides, {name}!</b>\n\n"
            "Tours auténticos a caballo y en carretón por Trinidad, Cuba.\n"
            "Guías locales. Precios justos. Experiencias de verdad.\n\n"
            "¿Qué te gustaría hacer?"
        ),
        "menu_book": "🐎 Reservar un tour",
        "menu_photos": "📸 Ver qué incluye",
        "menu_prices": "💰 Lista de precios",
        "menu_how": "ℹ️ Cómo funciona",
        "menu_extra": "💵 Dinero extra sugerido",
        "menu_reviews": "⭐ Ver reseñas",
        "menu_talk": "💬 Hablar con nosotros",
        "menu_lang": "🌐 Cambiar idioma",
        "back": "🔙 Atrás",
        "cancel": "❌ Cancelar",
        "choose_tour": "🐎 <b>¡Vamos a reservar tu tour!</b>\n\n<b>Paso 1/6</b> — Elige tu tour:",
        "how_many_adults": "👥 <b>Paso 2/6</b> — ¿Cuántos <b>adultos</b>?",
        "how_many_kids": "🧒 <b>Paso 3/6</b> — ¿Cuántos <b>niños</b>? (50% dcto)",
        "ask_date": "📅 <b>Paso 4/6</b> — Dime la <b>fecha</b> del tour.\n\nEjemplo: <code>2026-10-30</code>",
        "ask_name": "📝 <b>Paso 5/6</b> — ¿Cuál es tu <b>nombre completo</b>?",
        "ask_notes": (
            "💬 <b>Paso 6/6</b> — ¿Algo más que debamos saber?\n\n"
            "Ej: recogida en hotel, alergias, pedidos especiales...\n\n"
            "Si no tienes nada que añadir, pulsa <b>Saltar</b>."
        ),
        "skip": "⏭️ Saltar",
        "confirm_btn": "✅ Ya envié el pago",
        "yes": "✅ Sí, enviar",
        "no": "❌ No, revisar",
        "cancelled": "👍 Ok, cancelado. Escribe /start para volver al menú.",
        "summary_title": "📋 <b>Resumen de tu reserva</b>",
        "confirm_q": "¿Está todo bien?",
        "pay_instructions": (
            "💎 <b>Envía el depósito a:</b>\n"
            "<code>{wallet}</code>\n\n"
            "⚠️ <b>SOLO red BEP20 (Binance Smart Chain)</b>\n"
            "❌ NO uses Tron (TRC20) ni Ethereum (ERC20) — se perdería el dinero.\n\n"
            "📸 <b>Importante:</b> después de enviar, mándanos una <b>captura de pantalla</b> "
            "del pago aquí como respaldo."
        ),
        "reservation_received": (
            "✅ <b>¡Reserva recibida!</b>\n\n"
            "ID de reserva: <code>#{bid}</code>\n\n"
            "Estamos verificando tu pago en la blockchain. "
            "Te confirmamos por aquí en menos de 1 hora. 🐎\n\n"
            "📸 <i>No olvides enviarnos la captura del pago si aún no lo hiciste.</i>"
        ),
        "payment_confirmed": (
            "🎉 <b>¡Pago confirmado!</b>\n\n"
            "Tu reserva está lista. ¡Nos vemos en Trinidad! 🐎\n\n"
            "💵 Lleva el resto en efectivo (USD).\n\n"
            "⭐ Cuando termines el tour, nos encantaría leer tu reseña."
        ),
        "payment_rejected": (
            "⚠️ Todavía no podemos verificar tu pago. "
            "Por favor revisa la transacción y envíanos el hash por aquí."
        ),
        "completed_msg": (
            "🏁 <b>¡Tour completado!</b>\n\n"
            "Gracias por elegirnos. ¡Esperamos que lo hayas disfrutado! 🐎\n\n"
            "⭐ ¿Nos dejas una reseña? Nos ayuda muchísimo."
        ),
        "talk_msg": "💬 Escribe tu mensaje aquí abajo y te responderemos lo antes posible.",
        "no_notes": "— sin comentarios —",
        "invalid_date": "⚠️ Por favor envía una fecha válida (ej: 2026-10-30).",
        "invalid_name": "⚠️ Por favor envía tu nombre.",
        "reviews_title": "⭐ <b>Lo que dicen nuestros viajeros</b>",
        "reviews_body": "(Aún no hay reseñas — ¡sé el primero en dejarnos una después de tu tour!)",
        "prices_title": "💰 <b>Lista de precios</b>",
        "photos_title": "📸 <b>Un día con Trinidad Rides</b>",
        "photos_body": (
            "🐎 Campo cubano de verdad\n"
            "🥤 Guarapo fresco\n"
            "🍽️ Almuerzo criollo casero\n"
            "🍹 Cócteles y café cubano\n"
            "🏊 Baño en cascada de montaña\n"
            "🍯 Miel local y agua de coco\n\n"
            "<i>Fotos próximamente 📷</i>"
        ),
        "extra_title": "💵 <b>Dinero extra sugerido</b>",
        "extra_body": (
            "Recuerda que estás reservando un <b>servicio de tour</b>. "
            "El precio incluye el guía, el transporte y la experiencia principal, "
            "pero te recomendamos llevar algo de efectivo extra para:\n\n"
            "🍽️ Almorzar en el camino\n"
            "🥤 Refrescos, guarapo, agua de coco\n"
            "🍹 Cócteles o café en el campo\n"
            "🎁 Souvenirs artesanales\n"
            "💝 Propinas opcionales para el guía\n\n"
            "<i>Te recomendamos llevar entre $10 y $30 USD extra para disfrutar al máximo.</i>"
        ),
        "how_body": (
            "Así funciona 👇\n\n"
            "1️⃣ Eliges tu tour\n"
            "2️⃣ Nos dices fecha, personas y tu nombre\n"
            "3️⃣ Pagas el depósito en USDT (BEP20)\n"
            "4️⃣ Verificamos y confirmamos tu reserva\n"
            "5️⃣ Pagas el resto en efectivo al final\n\n"
            "⏱ Confirmamos en menos de 1 hora (hora de Cuba)."
        ),
        "book_now": "🐎 Reservar un tour",
        "back_to_menu": "⬅️ Volver al menú",
        "confirm_before_send": "🔎 Revisa antes de enviar:",
        "lang_choose": (
            "🌐 <b>Choose your language / Elige tu idioma</b>\n\n"
            "🇪🇸 Español\n🇬🇧 English\n🇫🇷 Français\n🇩🇪 Deutsch"
        ),
        "lang_set": "✅ Idioma configurado: Español",
    },
    "en": {
        "welcome": (
            "🐎 <b>Welcome to Trinidad Rides, {name}!</b>\n\n"
            "Authentic horseback & carretón tours in Trinidad, Cuba.\n"
            "Run by locals. Fair prices. Real experiences.\n\n"
            "What would you like to do?"
        ),
        "menu_book": "🐎 Book a tour",
        "menu_photos": "📸 See what's included",
        "menu_prices": "💰 Price list",
        "menu_how": "ℹ️ How it works",
        "menu_extra": "💵 Extra spending money",
        "menu_reviews": "⭐ See reviews",
        "menu_talk": "💬 Talk to us",
        "menu_lang": "🌐 Change language",
        "back": "🔙 Back",
        "cancel": "❌ Cancel",
        "choose_tour": "🐎 <b>Let's book your tour!</b>\n\n<b>Step 1/6</b> — Choose your tour:",
        "how_many_adults": "👥 <b>Step 2/6</b> — How many <b>adults</b>?",
        "how_many_kids": "🧒 <b>Step 3/6</b> — How many <b>kids</b>? (50% off)",
        "ask_date": "📅 <b>Step 4/6</b> — Send me the <b>date</b>.\n\nExample: <code>2026-10-30</code>",
        "ask_name": "📝 <b>Step 5/6</b> — What's your <b>full name</b>?",
        "ask_notes": (
            "💬 <b>Step 6/6</b> — Anything else we should know?\n\n"
            "E.g. hotel pickup, allergies, special requests...\n\n"
            "If nothing, tap <b>Skip</b>."
        ),
        "skip": "⏭️ Skip",
        "confirm_btn": "✅ I've sent the payment",
        "yes": "✅ Yes, send",
        "no": "❌ No, review",
        "cancelled": "👍 Ok, cancelled. Type /start to go back to the menu.",
        "summary_title": "📋 <b>Your booking summary</b>",
        "confirm_q": "Everything correct?",
        "pay_instructions": (
            "💎 <b>Send the deposit to:</b>\n"
            "<code>{wallet}</code>\n\n"
            "⚠️ <b>BEP20 (Binance Smart Chain) ONLY</b>\n"
            "❌ Do NOT use Tron (TRC20) or Ethereum (ERC20) — funds will be lost.\n\n"
            "📸 <b>Important:</b> after sending, please send us a <b>screenshot</b> "
            "of the payment here as proof."
        ),
        "reservation_received": (
            "✅ <b>Reservation received!</b>\n\n"
            "Booking ID: <code>#{bid}</code>\n\n"
            "We're verifying your payment on-chain. "
            "We'll confirm here within 1 hour. 🐎\n\n"
            "📸 <i>Don't forget to send us the payment screenshot if you haven't already.</i>"
        ),
        "payment_confirmed": (
            "🎉 <b>Payment confirmed!</b>\n\n"
            "Your booking is ready. See you in Trinidad! 🐎\n\n"
            "💵 Bring the rest in cash (USD).\n\n"
            "⭐ After the tour, we'd love to read your review."
        ),
        "payment_rejected": (
            "⚠️ We couldn't verify your payment yet. "
            "Please double-check and send us the hash here."
        ),
        "completed_msg": (
            "🏁 <b>Tour completed!</b>\n\n"
            "Thanks for choosing us. Hope you enjoyed it! 🐎\n\n"
            "⭐ Would you leave us a review? It helps a lot."
        ),
        "talk_msg": "💬 Type your message here and we'll reply ASAP.",
        "no_notes": "— no notes —",
        "invalid_date": "⚠️ Please send a valid date (e.g. 2026-10-30).",
        "invalid_name": "⚠️ Please send your name.",
        "reviews_title": "⭐ <b>What our travelers say</b>",
        "reviews_body": "(No reviews yet — be the first after your tour!)",
        "prices_title": "💰 <b>Price list</b>",
        "photos_title": "📸 <b>A day with Trinidad Rides</b>",
        "photos_body": (
            "🐎 Real Cuban countryside\n"
            "🥤 Fresh guarapo\n"
            "🍽️ Home-cooked criollo lunch\n"
            "🍹 Cuban cocktails & coffee\n"
            "🏊 Swim in a waterfall\n"
            "🍯 Local honey & coconut water\n\n"
            "<i>Photos coming soon 📷</i>"
        ),
        "extra_title": "💵 <b>Suggested extra spending money</b>",
        "extra_body": (
            "Remember you're booking a <b>tour service</b>. "
            "The price covers the guide, transport and main experience, "
            "but we recommend bringing extra cash for:\n\n"
            "🍽️ Lunch on the way\n"
            "🥤 Drinks, guarapo, coconut water\n"
            "🍹 Cocktails or coffee in the countryside\n"
            "🎁 Artisan souvenirs\n"
            "💝 Optional tips for your guide\n\n"
            "<i>We suggest $10-30 USD extra to enjoy it fully.</i>"
        ),
        "how_body": (
            "Here's how it works 👇\n\n"
            "1️⃣ Choose your tour\n"
            "2️⃣ Tell us date, people & name\n"
            "3️⃣ Pay deposit in USDT (BEP20)\n"
            "4️⃣ We verify and confirm\n"
            "5️⃣ Pay the rest in cash at the end\n\n"
            "⏱ We confirm within 1 hour (Cuba time)."
        ),
        "book_now": "🐎 Book a tour",
        "back_to_menu": "⬅️ Back to menu",
        "confirm_before_send": "🔎 Review before sending:",
        "lang_choose": (
            "🌐 <b>Choose your language / Elige tu idioma</b>\n\n"
            "🇪🇸 Español\n🇬🇧 English\n🇫🇷 Français\n🇩🇪 Deutsch"
        ),
        "lang_set": "✅ Language set: English",
    },
    "fr": {
        "welcome": (
            "🐎 <b>Bienvenue chez Trinidad Rides, {name} !</b>\n\n"
            "Des balades authentiques à cheval et en carretón à Trinidad, Cuba.\n"
            "Guides locaux. Prix justes. Vraies expériences.\n\n"
            "Que souhaitez-vous faire ?"
        ),
        "menu_book": "🐎 Réserver un tour",
        "menu_photos": "📸 Voir ce qui est inclus",
        "menu_prices": "💰 Liste des prix",
        "menu_how": "ℹ️ Comment ça marche",
        "menu_extra": "💵 Argent extra conseillé",
        "menu_reviews": "⭐ Voir les avis",
        "menu_talk": "💬 Nous parler",
        "menu_lang": "🌐 Changer de langue",
        "back": "🔙 Retour",
        "cancel": "❌ Annuler",
        "choose_tour": "🐎 <b>Réservons votre tour !</b>\n\n<b>Étape 1/6</b> — Choisissez votre tour :",
        "how_many_adults": "👥 <b>Étape 2/6</b> — Combien d'<b>adultes</b> ?",
        "how_many_kids": "🧒 <b>Étape 3/6</b> — Combien d'<b>enfants</b> ? (-50%)",
        "ask_date": "📅 <b>Étape 4/6</b> — Envoyez la <b>date</b>.\n\nExemple : <code>2026-10-30</code>",
        "ask_name": "📝 <b>Étape 5/6</b> — Quel est votre <b>nom complet</b> ?",
        "ask_notes": (
            "💬 <b>Étape 6/6</b> — Autre chose à savoir ?\n\n"
            "Ex : prise en charge à l'hôtel, allergies...\n\n"
            "Sinon, appuyez sur <b>Passer</b>."
        ),
        "skip": "⏭️ Passer",
        "confirm_btn": "✅ J'ai envoyé le paiement",
        "yes": "✅ Oui, envoyer",
        "no": "❌ Non, revoir",
        "cancelled": "👍 Annulé. Tapez /start pour revenir au menu.",
        "summary_title": "📋 <b>Résumé de votre réservation</b>",
        "confirm_q": "Tout est correct ?",
        "pay_instructions": (
            "💎 <b>Envoyez le dépôt à :</b>\n"
            "<code>{wallet}</code>\n\n"
            "⚠️ <b>Réseau BEP20 (Binance Smart Chain) UNIQUEMENT</b>\n"
            "❌ N'utilisez PAS Tron (TRC20) ni Ethereum (ERC20).\n\n"
            "📸 <b>Important :</b> après l'envoi, envoyez-nous une <b>capture d'écran</b>."
        ),
        "reservation_received": (
            "✅ <b>Réservation reçue !</b>\n\n"
            "ID : <code>#{bid}</code>\n\n"
            "Nous vérifions votre paiement. Confirmation sous 1h. 🐎\n\n"
            "📸 <i>N'oubliez pas la capture d'écran du paiement.</i>"
        ),
        "payment_confirmed": "🎉 <b>Paiement confirmé !</b>\n\nVotre réservation est prête. À bientôt à Trinidad ! 🐎",
        "payment_rejected": "⚠️ Paiement non vérifié. Vérifiez et envoyez-nous le hash.",
        "completed_msg": "🏁 <b>Tour terminé !</b>\n\nMerci ! Laissez-nous un avis ⭐",
        "talk_msg": "💬 Écrivez votre message ici.",
        "no_notes": "— sans commentaires —",
        "invalid_date": "⚠️ Envoyez une date valide (ex : 2026-10-30).",
        "invalid_name": "⚠️ Envoyez votre nom.",
        "reviews_title": "⭐ <b>Avis de nos voyageurs</b>",
        "reviews_body": "(Pas encore d'avis — soyez le premier !)",
        "prices_title": "💰 <b>Liste des prix</b>",
        "photos_title": "📸 <b>Une journée avec Trinidad Rides</b>",
        "photos_body": "🐎 Campagne cubaine\n🥤 Guarapo frais\n🍽️ Déjeuner criollo\n🏊 Cascade\n\n<i>Photos bientôt 📷</i>",
        "extra_title": "💵 <b>Argent extra conseillé</b>",
        "extra_body": (
            "Vous réservez un <b>service de tour</b>. Prévoyez de l'argent extra pour :\n\n"
            "🍽️ Déjeuner\n🥤 Boissons\n🍹 Cocktails\n🎁 Souvenirs\n💝 Pourboires\n\n"
            "<i>Nous conseillons 10-30 USD extra.</i>"
        ),
        "how_body": (
            "Voici comment ça marche 👇\n\n"
            "1️⃣ Choisir le tour\n2️⃣ Date, personnes, nom\n3️⃣ Dépôt USDT (BEP20)\n"
            "4️⃣ Vérification\n5️⃣ Reste en espèces\n\n⏱ Confirmation sous 1h."
        ),
        "book_now": "🐎 Réserver un tour",
        "back_to_menu": "⬅️ Retour au menu",
        "confirm_before_send": "🔎 Vérifiez avant d'envoyer :",
        "lang_choose": "🌐 <b>Choose your language / Elige tu idioma</b>\n\n🇪🇸 Español\n🇬🇧 English\n🇫🇷 Français\n🇩🇪 Deutsch",
        "lang_set": "✅ Langue définie : Français",
    },
    "de": {
        "welcome": (
            "🐎 <b>Willkommen bei Trinidad Rides, {name}!</b>\n\n"
            "Authentische Ausritte und Carretón-Touren in Trinidad, Kuba.\n"
            "Lokale Guides. Faire Preise. Echte Erlebnisse.\n\n"
            "Was möchtest du tun?"
        ),
        "menu_book": "🐎 Tour buchen",
        "menu_photos": "📸 Was ist inklusive",
        "menu_prices": "💰 Preisliste",
        "menu_how": "ℹ️ So funktioniert's",
        "menu_extra": "💵 Extra-Geld empfohlen",
        "menu_reviews": "⭐ Bewertungen",
        "menu_talk": "💬 Sprich mit uns",
        "menu_lang": "🌐 Sprache ändern",
        "back": "🔙 Zurück",
        "cancel": "❌ Abbrechen",
        "choose_tour": "🐎 <b>Buchen wir deine Tour!</b>\n\n<b>Schritt 1/6</b> — Wähle deine Tour:",
        "how_many_adults": "👥 <b>Schritt 2/6</b> — Wie viele <b>Erwachsene</b>?",
        "how_many_kids": "🧒 <b>Schritt 3/6</b> — Wie viele <b>Kinder</b>? (-50%)",
        "ask_date": "📅 <b>Schritt 4/6</b> — Sende das <b>Datum</b>.\n\nBeispiel: <code>2026-10-30</code>",
        "ask_name": "📝 <b>Schritt 5/6</b> — Dein <b>vollständiger Name</b>?",
        "ask_notes": "💬 <b>Schritt 6/6</b> — Noch etwas?\n\nZ.B. Hotelabholung, Allergien...\n\nSonst <b>Überspringen</b>.",
        "skip": "⏭️ Überspringen",
        "confirm_btn": "✅ Ich habe bezahlt",
        "yes": "✅ Ja, senden",
        "no": "❌ Nein, prüfen",
        "cancelled": "👍 Abgebrochen. Tippe /start für das Menü.",
        "summary_title": "📋 <b>Deine Buchungsübersicht</b>",
        "confirm_q": "Alles korrekt?",
        "pay_instructions": (
            "💎 <b>Sende die Anzahlung an:</b>\n"
            "<code>{wallet}</code>\n\n"
            "⚠️ <b>NUR BEP20 (Binance Smart Chain)</b>\n"
            "❌ NICHT Tron (TRC20) oder Ethereum (ERC20).\n\n"
            "📸 <b>Wichtig:</b> Nach dem Senden schicke uns einen <b>Screenshot</b>."
        ),
        "reservation_received": (
            "✅ <b>Reservierung erhalten!</b>\n\n"
            "Buchungs-ID: <code>#{bid}</code>\n\n"
            "Wir prüfen die Zahlung. Bestätigung in 1 Std. 🐎"
        ),
        "payment_confirmed": "🎉 <b>Zahlung bestätigt!</b>\n\nDeine Buchung ist fertig. Bis bald in Trinidad! 🐎",
        "payment_rejected": "⚠️ Zahlung nicht verifiziert. Bitte Hash senden.",
        "completed_msg": "🏁 <b>Tour abgeschlossen!</b>\n\nDanke! Hinterlasse uns eine Bewertung ⭐",
        "talk_msg": "💬 Schreibe deine Nachricht hier.",
        "no_notes": "— keine Notizen —",
        "invalid_date": "⚠️ Bitte gültiges Datum (z.B. 2026-10-30).",
        "invalid_name": "⚠️ Bitte deinen Namen senden.",
        "reviews_title": "⭐ <b>Was unsere Reisenden sagen</b>",
        "reviews_body": "(Noch keine Bewertungen — sei der Erste!)",
        "prices_title": "💰 <b>Preisliste</b>",
        "photos_title": "📸 <b>Ein Tag mit Trinidad Rides</b>",
        "photos_body": "🐎 Kubanisches Land\n🥤 Guarapo\n🍽️ Criollo-Mittagessen\n🏊 Wasserfall\n\n<i>Fotos bald 📷</i>",
        "extra_title": "💵 <b>Empfohlenes Extra-Geld</b>",
        "extra_body": (
            "Du buchst einen <b>Tour-Service</b>. Bringe Extra-Geld mit für:\n\n"
            "🍽️ Mittagessen\n🥤 Getränke\n🍹 Cocktails\n🎁 Souvenirs\n💝 Trinkgelder\n\n"
            "<i>Wir empfehlen 10-30 USD extra.</i>"
        ),
        "how_body": (
            "So funktioniert's 👇\n\n"
            "1️⃣ Tour wählen\n2️⃣ Datum, Personen, Name\n3️⃣ Anzahlung USDT (BEP20)\n"
            "4️⃣ Verifizierung\n5️⃣ Rest in Bar\n\n⏱ Bestätigung in 1 Std."
        ),
        "book_now": "🐎 Tour buchen",
        "back_to_menu": "⬅️ Zurück zum Menü",
        "confirm_before_send": "🔎 Prüfen vor dem Senden:",
        "lang_choose": "🌐 <b>Choose your language / Elige tu idioma</b>\n\n🇪🇸 Español\n🇬🇧 English\n🇫🇷 Français\n🇩🇪 Deutsch",
        "lang_set": "✅ Sprache gesetzt: Deutsch",
    },
}

LANG_FLAGS = {"es": "🇪🇸 Español", "en": "🇬🇧 English", "fr": "🇫🇷 Français", "de": "🇩🇪 Deutsch"}

# ============================================================
# ENV
# ============================================================
def load_env():
    env = {}
    try:
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    for key in ("BOT_TOKEN", "MY_CHAT_ID"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


ENV = load_env()
TOKEN = ENV.get("BOT_TOKEN")


def _parse_owner_id(raw):
    if not raw:
        return None
    try:
        return int(str(raw).strip())
    except (ValueError, TypeError):
        return None


OWNER_ID = _parse_owner_id(ENV.get("MY_CHAT_ID"))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ============================================================
# BASE DE DATOS
# ============================================================
def db_init():
    with closing(sqlite3.connect(DB_FILE)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                booking_id TEXT PRIMARY KEY,
                chat_id    INTEGER NOT NULL,
                name       TEXT,
                tour       TEXT,
                tour_key   TEXT,
                date       TEXT,
                adults     INTEGER,
                kids       INTEGER,
                notes      TEXT,
                language   TEXT,
                total      REAL,
                deposit    REAL,
                cash       REAL,
                status     TEXT,
                created    TEXT
            )
        """)
        conn.commit()


def db_save(b):
    with closing(sqlite3.connect(DB_FILE)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO bookings "
            "(booking_id, chat_id, name, tour, tour_key, date, adults, kids, "
            "notes, language, total, deposit, cash, status, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                b["booking_id"],
                b["chat_id"],
                b["name"],
                b["tour_name"],
                b["tour_key"],
                b["date"],
                b["adults"],
                b["kids"],
                b["notes"],
                b["language"],
                b["total"],
                b["deposit_amount"],
                b["cash_amount"],
                b.get("status", "pending"),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()


def db_get(booking_id):
    with closing(sqlite3.connect(DB_FILE)) as conn:
        row = conn.execute(
            "SELECT chat_id FROM bookings WHERE booking_id = ?", (booking_id,)
        ).fetchone()
    return row[0] if row else None


def db_set_status(booking_id, status):
    with closing(sqlite3.connect(DB_FILE)) as conn:
        conn.execute(
            "UPDATE bookings SET status = ? WHERE booking_id = ?",
            (status, booking_id),
        )
        conn.commit()


def db_del(booking_id):
    with closing(sqlite3.connect(DB_FILE)) as conn:
        conn.execute("DELETE FROM bookings WHERE booking_id = ?", (booking_id,))
        conn.commit()


def db_count():
    with closing(sqlite3.connect(DB_FILE)) as conn:
        return conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]


def db_active_list():
    with closing(sqlite3.connect(DB_FILE)) as conn:
        rows = conn.execute(
            "SELECT booking_id, name, tour, date, adults, kids, total, deposit, status "
            "FROM bookings WHERE status IN ('pending', 'verified') "
            "ORDER BY created DESC LIMIT 30"
        ).fetchall()
    return rows


# ============================================================
# HELPERS
# ============================================================
def esc(text) -> str:
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


_last_seen = {}


def is_rate_limited(chat_id):
    now = time.time()
    last = _last_seen.get(chat_id, 0)
    if now - last < COOLDOWN_SECONDS:
        return True
    _last_seen[chat_id] = now
    return False


def t(context, key, **kwargs):
    lang = context.user_data.get("lang", "es")
    if lang not in TEXTS:
        lang = "es"
    text = TEXTS[lang].get(key, TEXTS["es"].get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


def main_menu_keyboard(lang="es"):
    T = TEXTS.get(lang, TEXTS["es"])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(T["menu_book"], callback_data="book")],
        [InlineKeyboardButton(T["menu_photos"], callback_data="gallery")],
        [InlineKeyboardButton(T["menu_prices"], callback_data="prices")],
        [InlineKeyboardButton(T["menu_how"], callback_data="how")],
        [InlineKeyboardButton(T["menu_extra"], callback_data="extra")],
        [
            InlineKeyboardButton(T["menu_reviews"], callback_data="reviews"),
            InlineKeyboardButton(T["menu_talk"], callback_data="talk"),
        ],
        [InlineKeyboardButton(T["menu_lang"], callback_data="lang")],
    ])


def back_menu_keyboard(lang="es"):
    T = TEXTS.get(lang, TEXTS["es"])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(T["book_now"], callback_data="book")],
        [InlineKeyboardButton(T["back_to_menu"], callback_data="menu")],
    ])


# ============================================================
# COMANDOS PRINCIPALES
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "lang" not in context.user_data:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(LANG_FLAGS["es"], callback_data="setlang:es")],
            [InlineKeyboardButton(LANG_FLAGS["en"], callback_data="setlang:en")],
            [InlineKeyboardButton(LANG_FLAGS["fr"], callback_data="setlang:fr")],
            [InlineKeyboardButton(LANG_FLAGS["de"], callback_data="setlang:de")],
        ])
        await update.message.reply_text(
            "🌐 <b>Choose your language / Elige tu idioma</b>\n\n"
            "🇪🇸 Español\n🇬🇧 English\n🇫🇷 Français\n🇩🇪 Deutsch",
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
        return

    lang = context.user_data["lang"]
    nombre = update.effective_user.first_name or "traveler"
    await update.message.reply_text(
        t(context, "welcome", name=esc(nombre)),
        reply_markup=main_menu_keyboard(lang),
        parse_mode=ParseMode.HTML,
    )


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.split(":", 1)[1]
    if lang not in TEXTS:
        lang = "es"
    context.user_data["lang"] = lang

    nombre = update.effective_user.first_name or "traveler"
    try:
        await query.edit_message_text(
            t(context, "welcome", name=esc(nombre)),
            reply_markup=main_menu_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        await query.message.reply_text(
            t(context, "welcome", name=esc(nombre)),
            reply_markup=main_menu_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "🤖 <b>Comandos / Commands</b>\n\n"
        "/start — menú principal / main menu\n"
        "/status — estado del bot\n"
        "/help — esta ayuda\n"
        "/cancel — cancela una reserva\n"
    )
    if OWNER_ID and update.effective_chat.id == OWNER_ID:
        texto += "/reservas — ver reservas activas (solo dueño)\n"
    await update.message.reply_text(texto, parse_mode=ParseMode.HTML)


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(t(context, "cancelled"))


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        f"🔧 <b>Estado del bot</b>\n\n"
        f"Versión: <code>{esc(BOT_VERSION)}</code>\n"
        f"Red: <code>{esc(NETWORK_NAME)}</code>\n"
        f"Wallet: <code>{esc(WALLET_USDT)}</code>\n"
        f"Owner configurado: <code>{'SÍ' if OWNER_ID else 'NO'}</code>\n"
        f"Reservas guardadas: <code>{db_count()}</code>"
    )
    await update.message.reply_text(texto, parse_mode=ParseMode.HTML)


async def test_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not OWNER_ID:
        await update.message.reply_text("⚠️ Falta MY_CHAT_ID válido")
        return
    try:
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text="🔔 Test: si ves esto, las notificaciones funcionan.",
        )
        await update.message.reply_text("✅ Notificación enviada.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {esc(e)}")


async def list_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not OWNER_ID or update.effective_chat.id != OWNER_ID:
        await update.message.reply_text("⛔ Solo el dueño puede usar este comando.")
        return
    rows = db_active_list()
    if not rows:
        await update.message.reply_text("📋 No hay reservas activas.")
        return

    lines = [f"📋 <b>Reservas activas ({len(rows)})</b>\n"]
    for r in rows:
        bid, name, tour, date, adults, kids, total, deposit, status = r
        emoji = "🟡" if status == "pending" else "🟢"
        lines.append(
            f"{emoji} <b>#{esc(bid)}</b> — {esc(name)}\n"
            f"   {esc(tour)} · {esc(date)}\n"
            f"   👥 {adults}A/{kids}N · 💰 ${total:.2f} · 💎 ${deposit:.2f}\n"
            f"   Estado: <code>{esc(status)}</code>\n"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ============================================================
# BOTONES DEL MENÚ
# ============================================================
async def menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    lang = context.user_data.get("lang", "es")

    if data == "how":
        await query.edit_message_text(
            t(context, "how_body"),
            parse_mode=ParseMode.HTML,
            reply_markup=back_menu_keyboard(lang),
        )

    elif data == "gallery":
        await query.edit_message_text(
            f"{t(context, 'photos_title')}\n\n{t(context, 'photos_body')}",
            parse_mode=ParseMode.HTML,
            reply_markup=back_menu_keyboard(lang),
        )

    elif data == "prices":
        lines = [t(context, "prices_title"), ""]
        for k, tour in TOURS.items():
            name = tour["name_es"] if lang == "es" else tour["name_en"]
            price = tour["price"]
            dep = tour["deposit"]
            tipo = "por persona" if tour["type"] == "per-person" else "por tour"
            lines.append(
                f"{tour['emoji']} <b>{esc(name)}</b>\n"
                f"   💰 ${price} ({tipo})\n"
                f"   💎 Depósito: {dep}%\n"
            )
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=back_menu_keyboard(lang),
        )

    elif data == "extra":
        await query.edit_message_text(
            f"{t(context, 'extra_title')}\n\n{t(context, 'extra_body')}",
            parse_mode=ParseMode.HTML,
            reply_markup=back_menu_keyboard(lang),
        )

    elif data == "reviews":
        await query.edit_message_text(
            f"{t(context, 'reviews_title')}\n\n{t(context, 'reviews_body')}",
            parse_mode=ParseMode.HTML,
            reply_markup=back_menu_keyboard(lang),
        )

    elif data == "talk":
        await query.edit_message_text(
            t(context, "talk_msg"),
            parse_mode=ParseMode.HTML,
            reply_markup=back_menu_keyboard(lang),
        )

    elif data == "menu":
        nombre = update.effective_user.first_name or "traveler"
        await query.edit_message_text(
            t(context, "welcome", name=esc(nombre)),
            reply_markup=main_menu_keyboard(lang),
            parse_mode=ParseMode.HTML,
        )

    elif data == "lang":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(LANG_FLAGS["es"], callback_data="setlang:es")],
            [InlineKeyboardButton(LANG_FLAGS["en"], callback_data="setlang:en")],
            [InlineKeyboardButton(LANG_FLAGS["fr"], callback_data="setlang:fr")],
            [InlineKeyboardButton(LANG_FLAGS["de"], callback_data="setlang:de")],
            [InlineKeyboardButton(t(context, "back_to_menu"), callback_data="menu")],
        ])
        await query.edit_message_text(
            t(context, "lang_choose"),
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )


# ============================================================
# CONVERSACIÓN DE RESERVA
# ============================================================
def tour_label(tour, lang):
    name = tour["name_es"] if lang == "es" else tour["name_en"]
    return f"{tour['emoji']} {name} — ${tour['price']}"


async def start_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["booking"] = {}
    lang = context.user_data.get("lang", "es")

    keyboard = []
    for key, tour in TOURS.items():
        keyboard.append([InlineKeyboardButton(
            tour_label(tour, lang), callback_data=f"tour:{key}"
        )])
    keyboard.append([InlineKeyboardButton(t(context, "cancel"), callback_data="cancel_booking")])

    await query.edit_message_text(
        t(context, "choose_tour"),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return TOUR


async def tour_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data.split(":", 1)[1]
    if key not in TOURS:
        return TOUR

    context.user_data["booking"]["tour_key"] = key
    lang = context.user_data.get("lang", "es")
    tour = TOURS[key]

    keyboard = []
    row = []
    for i in range(1, 7):
        row.append(InlineKeyboardButton(str(i), callback_data=f"adults:{i}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton(t(context, "back"), callback_data="back_to_tour"),
        InlineKeyboardButton(t(context, "cancel"), callback_data="cancel_booking"),
    ])

    await query.edit_message_text(
        f"{tour['emoji']} <b>{esc(tour['name_es'] if lang == 'es' else tour['name_en'])}</b>\n\n"
        f"{t(context, 'how_many_adults')}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ADULTS


async def back_to_tour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("lang", "es")

    keyboard = []
    for key, tour in TOURS.items():
        keyboard.append([InlineKeyboardButton(
            tour_label(tour, lang), callback_data=f"tour:{key}"
        )])
    keyboard.append([InlineKeyboardButton(t(context, "cancel"), callback_data="cancel_booking")])

    await query.edit_message_text(
        t(context, "choose_tour"),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return TOUR


async def adults_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    n = int(query.data.split(":", 1)[1])
    if n < 1 or n > MAX_PEOPLE:
        return ADULTS

    context.user_data["booking"]["adults"] = n

    keyboard = []
    row = []
    for i in range(0, 6):
        row.append(InlineKeyboardButton(str(i), callback_data=f"kids:{i}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton(t(context, "back"), callback_data="back_to_adults"),
        InlineKeyboardButton(t(context, "cancel"), callback_data="cancel_booking"),
    ])

    await query.edit_message_text(
        t(context, "how_many_kids"),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return KIDS


async def back_to_adults(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("lang", "es")
    tour_key = context.user_data.get("booking", {}).get("tour_key")
    tour = TOURS.get(tour_key, list(TOURS.values())[0])

    keyboard = []
    row = []
    for i in range(1, 7):
        row.append(InlineKeyboardButton(str(i), callback_data=f"adults:{i}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton(t(context, "back"), callback_data="back_to_tour"),
        InlineKeyboardButton(t(context, "cancel"), callback_data="cancel_booking"),
    ])

    await query.edit_message_text(
        f"{tour['emoji']} <b>{esc(tour['name_es'] if lang == 'es' else tour['name_en'])}</b>\n\n"
        f"{t(context, 'how_many_adults')}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ADULTS


async def kids_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    n = int(query.data.split(":", 1)[1])
    context.user_data["booking"]["kids"] = n

    await query.edit_message_text(
        t(context, "ask_date"),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(t(context, "back"), callback_data="back_to_kids"),
                InlineKeyboardButton(t(context, "cancel"), callback_data="cancel_booking"),
            ]
        ]),
    )
    return DATE


async def back_to_kids(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = []
    row = []
    for i in range(0, 6):
        row.append(InlineKeyboardButton(str(i), callback_data=f"kids:{i}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton(t(context, "back"), callback_data="back_to_adults"),
        InlineKeyboardButton(t(context, "cancel"), callback_data="cancel_booking"),
    ])

    await query.edit_message_text(
        t(context, "how_many_kids"),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return KIDS


async def date_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if len(text) < 4 or len(text) > 40:
        await update.message.reply_text(t(context, "invalid_date"))
        return DATE

    context.user_data["booking"]["date"] = text
    await update.message.reply_text(
        f"📅 <b>{esc(text)}</b>\n\n{t(context, 'ask_name')}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t(context, "cancel"), callback_data="cancel_booking")]
        ]),
    )
    return NAME


async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text or len(text) > 100:
        await update.message.reply_text(t(context, "invalid_name"))
        return NAME

    context.user_data["booking"]["name"] = text
    await update.message.reply_text(
        t(context, "ask_notes"),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t(context, "skip"), callback_data="skip_notes")],
            [InlineKeyboardButton(t(context, "cancel"), callback_data="cancel_booking")],
        ]),
    )
    return NOTES


async def skip_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["booking"]["notes"] = ""
    await show_summary(query, context)
    return CONFIRM


async def notes_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    context.user_data["booking"]["notes"] = text[:500]
    await show_summary(update.message, context, is_message=True)
    return CONFIRM


async def show_summary(target, context, is_message=False):
    b = context.user_data["booking"]
    tour = TOURS[b["tour_key"]]
    lang = context.user_data.get("lang", "es")

    adults = b["adults"]
    kids = b["kids"]
    if tour["type"] == "per-person":
        total = adults * tour["price"] + kids * (tour["price"] / 2)
    else:
        total = tour["price"]

    deposit_pct = tour["deposit"]
    deposit = round(total * deposit_pct / 100, 2)
    cash = round(total - deposit, 2)

    b["tour_name"] = tour["name_es"] if lang == "es" else tour["name_en"]
    b["tour_emoji"] = tour["emoji"]
    b["total"] = round(total, 2)
    b["deposit_pct"] = deposit_pct
    b["deposit_amount"] = deposit
    b["cash_amount"] = cash

    notes = b.get("notes") or t(context, "no_notes")

    summary = (
        f"{t(context, 'summary_title')}\n\n"
        f"🎫 <b>{tour['emoji']} {esc(b['tour_name'])}</b>\n"
        f"📅 {esc(b['date'])}\n"
        f"👥 {adults} adult(s) · 🧒 {kids} kid(s)\n"
        f"📝 {esc(b['name'])}\n"
        f"💬 {esc(notes)}\n\n"
        f"💰 <b>Total: ${total:.2f}</b>\n"
        f"💎 <b>Deposit ({deposit_pct}%): ${deposit:.2f} USDT</b>\n"
        f"💵 Cash at the end: ${cash:.2f}\n\n"
        f"{t(context, 'pay_instructions').format(wallet=WALLET_USDT)}\n\n"
        f"{t(context, 'confirm_q')}"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(context, "confirm_btn"), callback_data="confirm_pay")],
        [InlineKeyboardButton(t(context, "cancel"), callback_data="cancel_booking")],
    ])

    if is_message:
        await target.reply_text(summary, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await target.edit_message_text(summary, parse_mode=ParseMode.HTML, reply_markup=kb)


async def payment_sent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    b = context.user_data.get("booking") or {}
    if "tour_name" not in b:
        await query.edit_message_text("⚠️ Something went wrong. /start again.")
        context.user_data.pop("booking", None)
        return ConversationHandler.END

    booking_id = uuid.uuid4().hex[:10].upper()
    client_chat_id = update.effective_chat.id
    lang = context.user_data.get("lang", "es")

    b["booking_id"] = booking_id
    b["chat_id"] = client_chat_id
    b["language"] = lang
    b["status"] = "pending"
    db_save(b)

    await query.edit_message_text(
        t(context, "reservation_received", bid=esc(booking_id)),
        parse_mode=ParseMode.HTML,
    )

    if OWNER_ID:
        bscscan_url = EXPLORER_BASE + WALLET_USDT
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Pago verificado", callback_data=f"verify_{booking_id}"
                ),
                InlineKeyboardButton(
                    "❌ No llegó", callback_data=f"reject_{booking_id}"
                ),
            ],
            [
                InlineKeyboardButton("🔍 BscScan", url=bscscan_url),
                InlineKeyboardButton(
                    "💬 Responder", url=f"tg://user?id={client_chat_id}"
                ),
            ],
        ])
        msg = (
            f"🔔 <b>#{esc(booking_id)}</b> · {esc(b['name'])}\n"
            f"🎫 {esc(b['tour_name'])}\n"
            f"📅 {esc(b['date'])} · 👥 {b['adults']}A/{b['kids']}N\n"
            f"🌐 {b['language'].upper()}\n"
            f"💰 ${b['total']:.2f} · 💎 ${b['deposit_amount']:.2f} · 💵 ${b['cash_amount']:.2f}\n"
            f"💬 {esc(b.get('notes') or '—')}"
        )
        try:
            await context.bot.send_message(
                chat_id=OWNER_ID,
                text=msg,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
            logger.info(f"Notificación enviada a {OWNER_ID}")
        except Exception as e:
            logger.error(f"Error notificando al dueño: {e}")

    context.user_data.pop("booking", None)
    return ConversationHandler.END


async def cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("booking", None)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(t(context, "cancelled"))
    else:
        await update.message.reply_text(t(context, "cancelled"))
    return ConversationHandler.END


async def start_and_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("booking", None)
    await start(update, context)
    return ConversationHandler.END


# ============================================================
# VERIFICAR / RECHAZAR / COMPLETAR
# ============================================================
async def verify_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    booking_id = query.data.replace("verify_", "")
    client_chat = db_get(booking_id)
    db_set_status(booking_id, "verified")

    if client_chat:
        try:
            lang = "es"
            await context.bot.send_message(
                chat_id=client_chat,
                text=TEXTS[lang]["payment_confirmed"],
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.error(f"No se pudo notificar cliente {booking_id}: {e}")

    await query.edit_message_text(
        f"✅ Reserva #{esc(booking_id)} verificada. Cliente notificado.\n\n"
        f"Usa /reservas para ver el estado.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏁 Marcar como completada", callback_data=f"complete_{booking_id}")],
            [InlineKeyboardButton("🔍 BscScan", url=EXPLORER_BASE + WALLET_USDT)],
        ]),
    )


async def reject_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    booking_id = query.data.replace("reject_", "")
    client_chat = db_get(booking_id)

    if client_chat:
        try:
            await context.bot.send_message(
                chat_id=client_chat,
                text=TEXTS["es"]["payment_rejected"],
            )
        except Exception as e:
            logger.error(f"No se pudo notificar cliente {booking_id}: {e}")

    await query.edit_message_text(
        f"❌ Reserva #{esc(booking_id)} — pago no verificado."
    )


async def complete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    booking_id = query.data.replace("complete_", "")
    client_chat = db_get(booking_id)

    if client_chat:
        try:
            await context.bot.send_message(
                chat_id=client_chat,
                text=TEXTS["es"]["completed_msg"],
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.error(f"No se pudo notificar cliente {booking_id}: {e}")
        db_del(booking_id)

    await query.edit_message_text(
        f"🏁 Reserva #{esc(booking_id)} completada. ¡Buen trabajo! 🐎"
    )


# ============================================================
# REENVÍO DE MENSAJES / CAPTURAS AL DUEÑO
# ============================================================
async def forward_to_owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if OWNER_ID and chat.id == OWNER_ID:
        return
    if chat.type != "private":
        return
    if msg.text and msg.text.startswith("/"):
        return

    if is_rate_limited(chat.id):
        await msg.reply_text("⏳ Espera unos segundos antes de enviar otro mensaje.")
        return

    if not OWNER_ID:
        await msg.reply_text("⚠️ El sistema de mensajes no está configurado.")
        return

    try:
        header = (
            f"💬 <b>De:</b> {esc(user.full_name)} (@{esc(user.username or '—')})\n"
            f"🆔 <code>{chat.id}</code>"
        )
        await context.bot.send_message(
            chat_id=OWNER_ID, text=header, parse_mode=ParseMode.HTML,
        )
        await msg.forward(chat_id=OWNER_ID)
        if msg.text:
            await msg.reply_text("📩 Mensaje enviado. Te responderemos pronto.")
    except Exception as e:
        logger.error(f"Error reenviando al owner: {e}")


# ============================================================
# ERROR HANDLER
# ============================================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Excepción: {update}", exc_info=context.error)


# ============================================================
# POST INIT
# ============================================================
async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start", "🐎 Menú principal"),
        BotCommand("help", "❓ Ayuda"),
        BotCommand("cancel", "❌ Cancelar reserva"),
    ])


# ============================================================
# MAIN
# ============================================================
def main():
    if not TOKEN:
        print("ERROR: No encontré BOT_TOKEN.")
        return
    if not OWNER_ID:
        print("⚠️ ADVERTENCIA: MY_CHAT_ID no configurado.")

    db_init()

    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    booking_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_booking, pattern="^book$")],
        states={
            TOUR: [
                CallbackQueryHandler(tour_chosen, pattern="^tour:"),
                CallbackQueryHandler(cancel_booking, pattern="^cancel_booking$"),
            ],
            ADULTS: [
                CallbackQueryHandler(adults_chosen, pattern="^adults:"),
                CallbackQueryHandler(back_to_tour, pattern="^back_to_tour$"),
                CallbackQueryHandler(cancel_booking, pattern="^cancel_booking$"),
            ],
            KIDS: [
                CallbackQueryHandler(kids_chosen, pattern="^kids:"),
                CallbackQueryHandler(back_to_adults, pattern="^back_to_adults$"),
                CallbackQueryHandler(cancel_booking, pattern="^cancel_booking$"),
            ],
            DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, date_received),
                CallbackQueryHandler(back_to_kids, pattern="^back_to_kids$"),
                CallbackQueryHandler(cancel_booking, pattern="^cancel_booking$"),
            ],
            NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, name_received),
                CallbackQueryHandler(cancel_booking, pattern="^cancel_booking$"),
            ],
            NOTES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, notes_received),
                CallbackQueryHandler(skip_notes, pattern="^skip_notes$"),
                CallbackQueryHandler(cancel_booking, pattern="^cancel_booking$"),
            ],
            CONFIRM: [
                CallbackQueryHandler(payment_sent, pattern="^confirm_pay$"),
                CallbackQueryHandler(cancel_booking, pattern="^cancel_booking$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_booking),
            CommandHandler("start", start_and_cancel),
        ],
        per_user=True,
        allow_reentry=True,
    )

    app.add_handler(booking_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("test", test_notify))
    app.add_handler(CommandHandler("reservas", list_bookings))

    app.add_handler(CallbackQueryHandler(set_language, pattern="^setlang:"))
    app.add_handler(CallbackQueryHandler(verify_handler, pattern="^verify_"))
    app.add_handler(CallbackQueryHandler(reject_handler, pattern="^reject_"))
    app.add_handler(CallbackQueryHandler(complete_handler, pattern="^complete_"))
    app.add_handler(CallbackQueryHandler(menu_button))

    app.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND,
        forward_to_owner,
    ))

    app.add_error_handler(error_handler)

    webhook_url = os.environ.get("WEBHOOK_URL")

    if webhook_url:
        import uvicorn
        from fastapi import FastAPI, Request

        web = FastAPI()

        @web.get("/")
        async def root():
            return {"status": "ok", "version": BOT_VERSION}

        @web.post(f"/webhook/{TOKEN}")
        async def webhook(request: Request):
            data = await request.json()
            update = Update.de_json(data, app.bot)
            await app.process_update(update)
            return {"ok": True}

        @web.on_event("startup")
        async def on_startup():
            await app.initialize()
            await app.start()
            await app.bot.set_webhook(
                url=f"{webhook_url.rstrip('/')}/webhook/{TOKEN}",
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
            )
            logger.info(f"✅ Webhook registrado: {webhook_url}/webhook/...")

        @web.on_event("shutdown")
        async def on_shutdown():
            await app.bot.delete_webhook()
            await app.stop()
            await app.shutdown()

        port = int(os.environ.get("PORT", "10000"))
        uvicorn.run(web, host="0.0.0.0", port=port)
    else:
        print("✅ Bot v7 corriendo en modo POLLING (local).")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
        main()
