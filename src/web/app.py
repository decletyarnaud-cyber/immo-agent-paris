"""
Streamlit web interface for Immo-Agent
Clean, organized interface with tabs and individual property analysis
"""
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from pathlib import Path
from urllib.parse import quote
import sys
import os

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.settings import WEB, CITIES, DEPARTMENTS, DATA_DIR


def ensure_dvf_data():
    """Download DVF data if not present (for cloud deployment)"""
    dvf_dir = DATA_DIR / "dvf"
    if not dvf_dir.exists() or not list(dvf_dir.glob("*.csv")):
        with st.spinner("Chargement des données DVF (première exécution)..."):
            try:
                from src.analysis.dvf_client import DVFClient
                dvf_client = DVFClient()
                for dept in DEPARTMENTS:
                    dvf_client.download_department_data(dept)
                st.success("Données DVF téléchargées!")
            except Exception as e:
                st.warning(f"DVF non disponible: {e}")


# Auto-download DVF data on startup
ensure_dvf_data()
from config.lawyers_catalog import find_lawyer_info, get_encheres_url
from src.storage.database import Database
from src.storage.models import PropertyType, AuctionStatus
from src.services.lawyer_finder import get_lawyer_finder
from src.analysis.multi_source_analyzer import MultiSourceAnalyzer
from src.analysis.neighborhood_analyzer import NeighborhoodAnalyzer

# Page configuration
st.set_page_config(
    page_title=WEB["title"],
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for cleaner interface with blue jeans textile texture
st.markdown("""
<style>
    /* Blue Jeans/Denim textile texture background */
    .stApp {
        background-color: #3d5a80;
        background-image:
            /* Diagonal denim weave pattern */
            repeating-linear-gradient(
                45deg,
                transparent,
                transparent 1px,
                rgba(255,255,255,0.04) 1px,
                rgba(255,255,255,0.04) 2px
            ),
            repeating-linear-gradient(
                -45deg,
                transparent,
                transparent 1px,
                rgba(0,0,0,0.06) 1px,
                rgba(0,0,0,0.06) 2px
            ),
            /* Horizontal threads */
            repeating-linear-gradient(
                0deg,
                transparent,
                transparent 4px,
                rgba(255,255,255,0.03) 4px,
                rgba(255,255,255,0.03) 5px
            ),
            /* Vertical threads */
            repeating-linear-gradient(
                90deg,
                transparent,
                transparent 4px,
                rgba(0,0,0,0.04) 4px,
                rgba(0,0,0,0.04) 5px
            );
    }

    /* All text white on denim background */
    .stApp, .stApp p, .stApp span, .stApp label, .stApp div {
        color: #f0f4f8 !important;
    }

    /* Headers in light color */
    .stApp h1, .stApp h2, .stApp h3, .stApp h4 {
        color: #ffffff !important;
    }

    /* Metrics styling */
    [data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-weight: 600;
    }

    [data-testid="stMetricLabel"] {
        color: #ccd6e0 !important;
    }

    [data-testid="stMetricDelta"] {
        color: #90EE90 !important;
    }

    /* Links */
    .stApp a {
        color: #7dd3fc !important;
    }

    /* Buttons */
    .stButton > button {
        background-color: #1e3a5f !important;
        color: white !important;
        border: 1px solid #5a7fa8 !important;
    }

    .stButton > button:hover {
        background-color: #2c4a6e !important;
        border-color: #7dd3fc !important;
    }

    /* Link buttons */
    .stLinkButton > a {
        background-color: #1e3a5f !important;
        color: white !important;
        border: 1px solid #5a7fa8 !important;
    }

    /* Expanders */
    .stExpander {
        background: rgba(30, 58, 95, 0.6) !important;
        border-radius: 8px;
        border: 1px solid #5a7fa8 !important;
    }

    /* DataFrames/Tables */
    .stDataFrame {
        background: rgba(30, 58, 95, 0.4) !important;
        border-radius: 8px;
    }

    .stDataFrame table {
        color: #f0f4f8 !important;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab"] {
        color: #ccd6e0 !important;
    }

    .stTabs [aria-selected="true"] {
        color: #ffffff !important;
    }

    /* Success/Warning/Error boxes */
    .stSuccess, .stInfo, .stWarning, .stError {
        color: #1a1a2e !important;
    }

    /* Selectbox and inputs */
    .stSelectbox > div > div, .stTextInput > div > div > input {
        background-color: rgba(30, 58, 95, 0.8) !important;
        color: #f0f4f8 !important;
        border-color: #5a7fa8 !important;
    }

    /* Caption text */
    .stCaption, small {
        color: #a0b4c8 !important;
    }

    /* Header styling */
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 0.5rem;
        color: #ffffff !important;
    }
    .sub-header {
        color: #ccd6e0 !important;
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .auction-card {
        border: 1px solid #5a7fa8;
        border-radius: 10px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        background: rgba(30, 58, 95, 0.5);
    }
    .property-info-card {
        background: rgba(30, 58, 95, 0.6);
        border-radius: 12px;
        padding: 1.5rem;
        border: 1px solid #5a7fa8;
        margin-bottom: 1rem;
    }
    .visit-date-badge {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 8px;
        display: inline-block;
        margin: 0.25rem;
        font-weight: 500;
    }
    .score-badge {
        display: inline-block;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        font-weight: bold;
        font-size: 0.9rem;
    }
    .score-high { background: #10b981; color: white; }
    .score-medium { background: #f59e0b; color: white; }
    .score-low { background: #ef4444; color: white; }
    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem;
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 1.1rem;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)


# Initialize services
@st.cache_resource
def get_database():
    return Database()


@st.cache_resource
def get_lawyer_finder_cached():
    return get_lawyer_finder()


@st.cache_resource
def get_multi_source_analyzer():
    return MultiSourceAnalyzer()


def main():
    """Main application"""
    # Header
    st.markdown('<p class="main-header">🏠 Immo-Agent</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Enchères Judiciaires Immobilières • Paris • Hauts-de-Seine • Seine-Saint-Denis • Val-de-Marne</p>', unsafe_allow_html=True)

    db = get_database()

    # Show notification if auction selected from calendar
    if st.session_state.get('selected_auction_id'):
        st.toast("📋 Annonce sélectionnée ! Allez à l'onglet 'Analyse détaillée'", icon="📅")

    # Main tabs
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 Tableau de bord",
        "📅 Calendrier visites",
        "🔍 Toutes les enchères",
        "⭐ Opportunités",
        "📈 Prix par quartier",
        "📋 Analyse détaillée",
        "⚙️ Paramètres"
    ])

    with tab1:
        show_dashboard(db)

    with tab2:
        show_visits_calendar(db)

    with tab3:
        show_all_auctions(db)

    with tab4:
        show_opportunities(db)

    with tab5:
        show_neighborhood_prices()

    with tab6:
        show_detailed_analysis(db)

    with tab7:
        show_settings(db)


def show_visits_calendar(db: Database):
    """Interactive calendar showing upcoming property visits"""
    st.subheader("📅 Calendrier des Visites")

    # Get all upcoming auctions with visit dates
    auctions = db.get_upcoming_auctions(days=90)

    # Collect all visits
    all_visits = []
    for auction in auctions:
        if auction.dates_visite:
            for visite in auction.dates_visite:
                if visite.date() >= date.today():
                    all_visits.append({
                        'date': visite,
                        'auction': auction
                    })

    # Sort visits by date
    all_visits.sort(key=lambda x: x['date'])

    if not all_visits:
        st.info("Aucune visite programmée dans les 90 prochains jours")
        return

    # Week navigation
    col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])

    # Initialize week offset in session state
    if 'week_offset' not in st.session_state:
        st.session_state.week_offset = 0

    with col_nav1:
        if st.button("◀ Semaine précédente"):
            st.session_state.week_offset -= 1

    with col_nav3:
        if st.button("Semaine suivante ▶"):
            st.session_state.week_offset += 1

    # Calculate current week dates
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday()) + timedelta(weeks=st.session_state.week_offset)
    end_of_week = start_of_week + timedelta(days=6)

    with col_nav2:
        st.markdown(f"### 📆 {start_of_week.strftime('%d/%m')} - {end_of_week.strftime('%d/%m/%Y')}")

    # Filter visits for current week
    week_visits = [v for v in all_visits if start_of_week <= v['date'].date() <= end_of_week]

    # Summary metrics
    st.markdown("---")
    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)

    with metric_col1:
        st.metric("📅 Cette semaine", len(week_visits))
    with metric_col2:
        today_visits = len([v for v in all_visits if v['date'].date() == today])
        st.metric("📍 Aujourd'hui", today_visits)
    with metric_col3:
        next_7_days = len([v for v in all_visits if today <= v['date'].date() <= today + timedelta(days=7)])
        st.metric("🗓️ 7 prochains jours", next_7_days)
    with metric_col4:
        st.metric("📋 Total à venir", len(all_visits))

    st.markdown("---")

    # Calendar grid - 7 days
    days_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    day_cols = st.columns(7)

    for i, col in enumerate(day_cols):
        current_date = start_of_week + timedelta(days=i)
        is_today = current_date == today
        is_past = current_date < today

        with col:
            # Day header
            header_style = "background:#10b981; color:white;" if is_today else "background:rgba(30, 58, 95, 0.8); color:#ccd6e0;" if not is_past else "background:rgba(30, 58, 95, 0.4); color:#6b7280;"
            st.markdown(f"""
            <div style='{header_style} padding:0.5rem; border-radius:8px 8px 0 0; text-align:center; font-weight:600'>
                {days_fr[i]}<br/>
                <span style='font-size:1.2em'>{current_date.strftime('%d')}</span>
            </div>
            """, unsafe_allow_html=True)

            # Get visits for this day
            day_visits = [v for v in week_visits if v['date'].date() == current_date]

            if day_visits:
                for idx, visit in enumerate(day_visits):
                    auction = visit['auction']
                    heure = visit['date'].strftime('%Hh%M')
                    type_bien = auction.type_bien.value if auction.type_bien else "Bien"
                    ville = auction.ville or "?"
                    mise_prix = f"{auction.mise_a_prix:,.0f}€".replace(",", " ") if auction.mise_a_prix else "?"

                    # Card color based on opportunity
                    decote = auction.decote_pourcentage or 0
                    if decote >= 30:
                        card_color = "#10b981"
                        badge = "🔥"
                    elif decote >= 20:
                        card_color = "#f59e0b"
                        badge = "⭐"
                    else:
                        card_color = "#3b82f6"
                        badge = "🏠"

                    # Unique key for this visit
                    visit_key = f"visit_{current_date}_{idx}_{auction.id}"

                    # Clickable popover for each visit
                    with st.popover(f"{heure} {badge}", use_container_width=True):
                        st.markdown(f"### {type_bien.capitalize()} à {ville}")
                        st.markdown(f"**📍 Adresse:** {auction.adresse or 'Non précisée'}")
                        st.markdown(f"**💰 Mise à prix:** {mise_prix}")
                        if auction.surface:
                            st.markdown(f"**📐 Surface:** {auction.surface:.0f} m²")
                        if decote > 0:
                            st.markdown(f"**📉 Décote:** {decote:.0f}%")
                        st.markdown(f"**📅 Visite:** {visit['date'].strftime('%d/%m/%Y à %Hh%M')}")
                        if auction.date_vente:
                            st.markdown(f"**🔨 Vente:** {auction.date_vente.strftime('%d/%m/%Y')}")

                        st.markdown("---")

                        # Button to go to detailed analysis
                        if st.button("📋 Voir analyse détaillée", key=f"analyze_{visit_key}", use_container_width=True):
                            st.session_state.selected_auction_id = auction.id
                            st.info("👆 Cliquez sur l'onglet **📋 Analyse détaillée** pour voir l'analyse complète")
                            st.rerun()

                        if auction.url:
                            st.link_button("🔗 Voir l'annonce", auction.url, use_container_width=True)

                        if auction.avocat_email:
                            mailto = build_email_link(auction)
                            st.link_button("📧 Contacter avocat", mailto, use_container_width=True)
            else:
                st.markdown("""
                <div style='background:rgba(30, 58, 95, 0.3); padding:1rem; margin:0.3rem 0; border-radius:4px; text-align:center; color:#6b7280; font-size:0.8em'>
                    -
                </div>
                """, unsafe_allow_html=True)

    # Detailed list of this week's visits
    st.markdown("---")
    st.markdown("### 📋 Détail des visites de la semaine")

    if week_visits:
        for visit in week_visits:
            auction = visit['auction']
            visite_date = visit['date']
            type_bien = auction.type_bien.value if auction.type_bien else "Bien"
            mise_prix = f"{auction.mise_a_prix:,.0f}€".replace(",", " ") if auction.mise_a_prix else "?"
            surface = f"{auction.surface:.0f}m²" if auction.surface else "?"
            decote = auction.decote_pourcentage or 0

            # Urgency indicator
            days_until = (visite_date.date() - today).days
            if days_until == 0:
                urgency = "🔴 AUJOURD'HUI"
                urgency_color = "#ef4444"
            elif days_until == 1:
                urgency = "🟠 DEMAIN"
                urgency_color = "#f59e0b"
            elif days_until <= 3:
                urgency = f"🟡 Dans {days_until}j"
                urgency_color = "#eab308"
            else:
                urgency = f"🟢 Dans {days_until}j"
                urgency_color = "#10b981"

            col1, col2, col3, col4 = st.columns([2, 3, 2, 1])

            with col1:
                st.markdown(f"""
                <div style='background:{urgency_color}; color:white; padding:0.3rem 0.5rem; border-radius:6px; text-align:center; font-weight:600'>
                    {visite_date.strftime('%A %d/%m')}<br/>
                    {visite_date.strftime('%Hh%M')}
                </div>
                """, unsafe_allow_html=True)

            with col2:
                st.markdown(f"**{type_bien.capitalize()} à {auction.ville}**")
                st.caption(f"{auction.adresse or 'Adresse non précisée'}")

            with col3:
                st.markdown(f"**{mise_prix}** • {surface}")
                if decote > 0:
                    st.markdown(f"📉 Décote: **{decote:.0f}%**")

            with col4:
                if auction.url:
                    st.link_button("Voir", auction.url, use_container_width=True)

            st.markdown("<hr style='margin:0.5rem 0; border-color:rgba(90,127,168,0.3)'>", unsafe_allow_html=True)
    else:
        st.info("Aucune visite programmée cette semaine")

    # Quick access to all upcoming visits
    with st.expander("📆 Toutes les visites à venir"):
        for visit in all_visits[:20]:
            auction = visit['auction']
            visite_date = visit['date']
            type_bien = auction.type_bien.value if auction.type_bien else "Bien"
            st.markdown(f"**{visite_date.strftime('%d/%m/%Y %Hh%M')}** - {type_bien} à {auction.ville} - {auction.mise_a_prix:,.0f}€".replace(",", " ") if auction.mise_a_prix else f"**{visite_date.strftime('%d/%m/%Y %Hh%M')}** - {type_bien} à {auction.ville}")


def show_dashboard(db: Database):
    """Dashboard with key metrics"""
    stats = db.get_stats()

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="📦 Total enchères",
            value=stats.get("total_auctions", 0)
        )

    with col2:
        st.metric(
            label="📅 À venir (30j)",
            value=stats.get("upcoming", 0)
        )

    with col3:
        # Count opportunities
        auctions = db.get_upcoming_auctions(days=60)
        opportunities = len([a for a in auctions if (a.decote_pourcentage or 0) >= 20])
        st.metric(
            label="⭐ Opportunités",
            value=opportunities
        )

    with col4:
        st.metric(
            label="👨‍⚖️ Avocats",
            value=stats.get("total_lawyers", 0)
        )

    st.markdown("---")

    # ==================== NOUVEAUTÉS SECTION ====================
    st.subheader("🆕 Nouveautés")
    newest = db.get_newest_auctions(limit=5)

    if newest:
        for auction in newest:
            display_nouveaute_card(auction)
    else:
        st.info("Aucune nouvelle enchère récemment ajoutée")

    st.markdown("---")

    # Two columns layout
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.subheader("📅 Prochaines ventes")
        upcoming = db.get_upcoming_auctions(days=30)

        if upcoming:
            for auction in upcoming[:8]:
                display_auction_row(auction)
        else:
            st.info("Aucune enchère à venir dans les 30 prochains jours")

    with col_right:
        st.subheader("🏆 Top Opportunités")
        top = db.get_top_opportunities(limit=5)

        if top:
            for auction in top:
                display_opportunity_card(auction)
        else:
            st.info("Lancez une analyse pour découvrir les opportunités")


def show_all_auctions(db: Database):
    """All auctions with filters"""
    st.subheader("🔍 Toutes les enchères")

    # Filters row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        ville_filter = st.selectbox(
            "Ville",
            ["Toutes"] + list(CITIES.keys()),
            format_func=lambda x: x.replace("-", " ").title() if x != "Toutes" else x
        )

    with col2:
        type_filter = st.selectbox(
            "Type de bien",
            ["Tous", "appartement", "maison", "local_commercial", "parking", "terrain"],
            format_func=lambda x: x.replace("_", " ").title()
        )

    with col3:
        budget_max = st.number_input("Budget max (€)", min_value=0, value=0, step=10000)

    with col4:
        only_opportunities = st.checkbox("Opportunités uniquement (décote > 20%)")

    # Search
    search_params = {}
    if ville_filter != "Toutes":
        search_params["ville"] = ville_filter.replace("-", " ").title()
    if type_filter != "Tous":
        search_params["type_bien"] = PropertyType(type_filter)
    if budget_max > 0:
        search_params["prix_max"] = budget_max

    results = db.search_auctions(**search_params)

    if only_opportunities:
        results = [r for r in results if (r.decote_pourcentage or 0) >= 20]

    st.markdown(f"**{len(results)} enchère(s) trouvée(s)**")
    st.markdown("---")

    # Results
    if results:
        # Interactive list view with clickable rows
        for idx, auction in enumerate(results):
            date_str = auction.date_vente.strftime("%d/%m/%Y") if auction.date_vente else "?"
            type_bien = auction.type_bien.value if auction.type_bien else "Bien"
            mise_prix = f"{auction.mise_a_prix:,.0f}€".replace(",", " ") if auction.mise_a_prix else "?"
            surface = f"{auction.surface:.0f}m²" if auction.surface else "?"
            decote = auction.decote_pourcentage or 0
            score = auction.score_opportunite or 0

            # Row color based on opportunity
            if decote >= 30:
                border_color = "#10b981"
            elif decote >= 20:
                border_color = "#f59e0b"
            else:
                border_color = "#3b82f6"

            col1, col2, col3, col4, col5, col6 = st.columns([2, 3, 1, 1, 1, 2])

            with col1:
                st.markdown(f"**{date_str}**")
                st.caption(f"{type_bien}")

            with col2:
                st.markdown(f"**{auction.ville}**")
                st.caption(f"{auction.adresse or ''}"[:30])

            with col3:
                st.markdown(f"**{surface}**")

            with col4:
                st.markdown(f"**{mise_prix}**")

            with col5:
                if decote > 0:
                    st.markdown(f"<span style='color:{border_color}; font-weight:600'>-{decote:.0f}%</span>", unsafe_allow_html=True)
                else:
                    st.markdown("-")

            with col6:
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button("📋", key=f"analyze_list_{idx}", help="Analyse détaillée"):
                        st.session_state.selected_auction_id = auction.id
                        st.toast("👆 Allez à l'onglet 'Analyse détaillée'", icon="📋")
                with btn_col2:
                    if auction.url:
                        st.link_button("🔗", auction.url, help="Voir l'annonce")

            st.markdown("<hr style='margin:0.3rem 0; border-color:rgba(90,127,168,0.2)'>", unsafe_allow_html=True)
    else:
        st.info("Aucune enchère ne correspond à vos critères")


def show_opportunities(db: Database):
    """Opportunities page sorted by visit date and price differential"""
    st.subheader("⭐ Opportunités - Prochaines visites")

    auctions = db.get_upcoming_auctions(days=90)

    if not auctions:
        st.info("Aucune enchère à analyser")
        return

    # Calculate price differential and sort by visit date
    opportunities = []
    for a in auctions:
        # Get dates_visite safely
        dates_visite = getattr(a, 'dates_visite', []) or []

        # Calculate price differential
        differentiel = 0
        if a.prix_marche_estime and a.mise_a_prix:
            differentiel = a.prix_marche_estime - a.mise_a_prix

        # Find next visit date
        next_visit = None
        if dates_visite:
            future_visits = [d for d in dates_visite if d.date() >= date.today()]
            if future_visits:
                next_visit = min(future_visits)

        opportunities.append({
            'auction': a,
            'differentiel': differentiel,
            'decote': a.decote_pourcentage or 0,
            'next_visit': next_visit,
            'date_vente': a.date_vente
        })

    # Sort: first by next visit date (soonest first), then by price differential (highest first)
    opportunities.sort(key=lambda x: (
        x['next_visit'] if x['next_visit'] else datetime(2099, 12, 31),
        -x['differentiel']
    ))

    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        with_visits = len([o for o in opportunities if o['next_visit']])
        st.metric("📅 Avec visite programmée", with_visits)
    with col2:
        high_diff = len([o for o in opportunities if o['differentiel'] > 50000])
        st.metric("💰 Gain potentiel > 50k€", high_diff)
    with col3:
        high_decote = len([o for o in opportunities if o['decote'] >= 30])
        st.metric("📉 Décote > 30%", high_decote)
    with col4:
        total_diff = sum(o['differentiel'] for o in opportunities if o['differentiel'] > 0)
        st.metric("💎 Potentiel total", f"{total_diff:,.0f}€".replace(",", " "))

    st.markdown("---")

    # Display opportunities
    for opp in opportunities:
        auction = opp['auction']
        differentiel = opp['differentiel']
        decote = opp['decote']
        next_visit = opp['next_visit']

        # Card styling based on opportunity level
        if differentiel > 100000:
            border_color = "#10b981"  # Green - exceptional
            badge = "🌟 EXCEPTIONNEL"
        elif differentiel > 50000:
            border_color = "#f59e0b"  # Orange - good
            badge = "⭐ OPPORTUNITÉ"
        elif differentiel > 20000:
            border_color = "#3b82f6"  # Blue - interesting
            badge = "✨ INTÉRESSANT"
        else:
            border_color = "#6b7280"  # Gray
            badge = ""

        with st.container():
            # Header with visit date prominently displayed
            visit_html = ""
            if next_visit:
                days_until = (next_visit.date() - date.today()).days
                if days_until <= 7:
                    visit_color = "#ef4444"  # Red - urgent
                    visit_text = f"🔴 VISITE DANS {days_until}J"
                elif days_until <= 14:
                    visit_color = "#f59e0b"  # Orange
                    visit_text = f"🟠 Visite dans {days_until}j"
                else:
                    visit_color = "#10b981"  # Green
                    visit_text = f"🟢 Visite le {next_visit.strftime('%d/%m')}"
                visit_html = f"<span style='background:{visit_color}; color:white; padding:0.3rem 0.6rem; border-radius:6px; font-weight:600; margin-right:0.5rem'>{visit_text}</span>"

            type_bien = auction.type_bien.value if auction.type_bien else "Bien"

            # Format prices safely
            mise_prix_str = f"{auction.mise_a_prix:,.0f}€".replace(",", " ") if auction.mise_a_prix else "?"
            valeur_marche_str = f"{auction.prix_marche_estime:,.0f}€".replace(",", " ") if auction.prix_marche_estime else "?"
            diff_str = f"+{differentiel:,.0f}€".replace(",", " ") if differentiel > 0 else "?"

            st.markdown(f"""
            <div style='background:rgba(30, 58, 95, 0.6); padding:1rem; border-radius:10px; margin-bottom:1rem; border-left:4px solid {border_color}'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem'>
                    <span style='font-size:1.2em; font-weight:600; color:#f0f4f8'>{type_bien.capitalize()} à {auction.ville}</span>
                    <span>{visit_html}<span style='color:{border_color}; font-weight:600'>{badge}</span></span>
                </div>
                <div style='color:#a0b4c8; margin-bottom:0.8rem'>{auction.adresse or ''}</div>
                <div style='display:flex; gap:2rem; flex-wrap:wrap'>
                    <div>
                        <div style='color:#a0b4c8; font-size:0.8em'>Mise à prix</div>
                        <div style='font-size:1.3em; font-weight:600; color:#f0f4f8'>{mise_prix_str}</div>
                    </div>
                    <div>
                        <div style='color:#a0b4c8; font-size:0.8em'>Valeur marché</div>
                        <div style='font-size:1.3em; font-weight:600; color:#f0f4f8'>{valeur_marche_str}</div>
                    </div>
                    <div>
                        <div style='color:#a0b4c8; font-size:0.8em'>💰 Gain potentiel</div>
                        <div style='font-size:1.3em; font-weight:600; color:{border_color}'>{diff_str}</div>
                    </div>
                    <div>
                        <div style='color:#a0b4c8; font-size:0.8em'>📉 Décote</div>
                        <div style='font-size:1.3em; font-weight:600; color:{border_color}'>{decote:.0f}%</div>
                    </div>
                    <div>
                        <div style='color:#a0b4c8; font-size:0.8em'>📐 Surface</div>
                        <div style='font-size:1.1em; color:#f0f4f8'>{auction.surface or '?'} m²</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Action buttons
            btn_col1, btn_col2, btn_col3 = st.columns(3)
            with btn_col1:
                if auction.url:
                    st.link_button("🔗 Voir l'annonce", auction.url, use_container_width=True)
            with btn_col2:
                if auction.avocat_email:
                    mailto = build_email_link(auction)
                    st.link_button("📧 Contacter avocat", mailto, use_container_width=True)
            with btn_col3:
                if auction.date_vente:
                    st.markdown(f"**Vente:** {auction.date_vente.strftime('%d/%m/%Y')}")

    if not opportunities:
        st.info("Aucune enchère à venir")


def show_detailed_analysis(db: Database):
    """Individual property analysis"""
    st.subheader("📋 Analyse détaillée d'un bien")

    auctions = db.get_all_auctions(limit=100)

    if not auctions:
        st.info("Aucune enchère disponible")
        return

    # Property selector - build options dict with auction id as secondary key
    options = {}
    options_by_id = {}
    for a in auctions:
        label = f"{a.ville} - {a.type_bien.value if a.type_bien else 'Bien'} {a.surface or '?'}m² - {a.mise_a_prix:,.0f}€" if a.mise_a_prix else f"{a.ville} - {a.type_bien.value if a.type_bien else 'Bien'}"
        options[label] = a
        options_by_id[a.id] = label

    # Check if coming from calendar with pre-selected auction
    default_index = 0
    if st.session_state.get('selected_auction_id'):
        selected_id = st.session_state.selected_auction_id
        if selected_id in options_by_id:
            label = options_by_id[selected_id]
            options_list = list(options.keys())
            if label in options_list:
                default_index = options_list.index(label)
                st.success(f"📅 Annonce sélectionnée depuis le calendrier des visites")
        # Clear the selection after use
        st.session_state.selected_auction_id = None

    selected_label = st.selectbox(
        "Sélectionnez un bien à analyser",
        options=list(options.keys()),
        index=default_index
    )

    if selected_label:
        auction = options[selected_label]
        display_property_analysis(auction)


def show_neighborhood_prices():
    """Display adjudication results analysis - judicial auctions only"""
    st.subheader("📈 Résultats d'Adjudication par Quartier")
    st.markdown("*Analyse des prix de vente aux enchères judiciaires uniquement (pas de données DVF)*")

    db = get_database()

    # Get total count
    total_results = db.get_adjudication_count()

    col1, col2 = st.columns([2, 1])
    with col1:
        st.info(f"""
        **{total_results} résultats d'adjudication** dans la base de données.

        Sources : Eklar, Licitor, saisie manuelle
        """)
    with col2:
        dept_filter = st.selectbox("Département", ["13 - Bouches-du-Rhône", "83 - Var", "Tous"])
        dept_prefix = dept_filter.split(" ")[0] if dept_filter != "Tous" else None

    # Get stats by postal code
    if dept_prefix:
        stats = db.get_adjudication_stats_by_postal(dept_prefix)
    else:
        stats_13 = db.get_adjudication_stats_by_postal("13")
        stats_83 = db.get_adjudication_stats_by_postal("83")
        stats = stats_13 + stats_83

    if stats:
        st.markdown("### 📊 Prix moyens par quartier (enchères judiciaires)")

        data = []
        for s in stats:
            data.append({
                "Code Postal": s["code_postal"],
                "Ville": s["ville"] or "-",
                "Nb ventes": s["nb_ventes"],
                "Prix moyen": f"{s['prix_moyen']:,.0f} €".replace(",", " ") if s["prix_moyen"] else "-",
                "Prix/m² moyen": f"{s['prix_m2_moyen']:,.0f} €".replace(",", " ") if s.get("prix_m2_moyen") else "-",
                "Surface moy.": f"{s['surface_moyenne']:.0f} m²" if s.get("surface_moyenne") else "-",
            })

        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Show detailed results
        with st.expander("Voir tous les résultats détaillés"):
            all_results = db.get_all_adjudication_results(dept_prefix, limit=200)
            if all_results:
                detail_data = []
                for r in all_results:
                    detail_data.append({
                        "Date": r.get("date_adjudication") or "-",
                        "Code Postal": r["code_postal"],
                        "Ville": r.get("ville") or "-",
                        "Type": r.get("type_bien") or "-",
                        "Surface": f"{r['surface']:.0f} m²" if r.get("surface") else "-",
                        "Prix adjugé": f"{r['prix_adjuge']:,.0f} €".replace(",", " "),
                        "Prix/m²": f"{r['prix_m2']:,.0f} €".replace(",", " ") if r.get("prix_m2") else "-",
                        "Source": r.get("source") or "-",
                    })
                df_detail = pd.DataFrame(detail_data)
                st.dataframe(df_detail, use_container_width=True, hide_index=True)
    else:
        st.warning("Aucun résultat d'adjudication enregistré pour le moment.")

    # Manual entry section
    st.markdown("---")
    st.markdown("### ➕ Ajouter un résultat d'adjudication")

    with st.expander("Formulaire de saisie manuelle"):
        col1, col2 = st.columns(2)

        with col1:
            adj_date = st.date_input("Date d'adjudication")
            adj_adresse = st.text_input("Adresse du bien")
            adj_cp = st.text_input("Code postal", max_chars=5)
            adj_ville = st.text_input("Ville")

        with col2:
            adj_type = st.selectbox("Type de bien", ["Appartement", "Maison", "Local", "Terrain", "Parking"])
            adj_surface = st.number_input("Surface (m²)", min_value=0.0, step=1.0)
            adj_mise_prix = st.number_input("Mise à prix (€)", min_value=0.0, step=1000.0)
            adj_prix = st.number_input("Prix adjugé (€)", min_value=0.0, step=1000.0)

        adj_tribunal = st.selectbox("Tribunal", [
            "Tribunal Judiciaire de Marseille",
            "Tribunal Judiciaire d'Aix-en-Provence",
            "Tribunal Judiciaire de Toulon"
        ])

        if st.button("Enregistrer le résultat"):
            if adj_cp and adj_prix > 0:
                try:
                    result_id = db.save_adjudication_result(
                        source="Saisie manuelle",
                        code_postal=adj_cp,
                        prix_adjuge=adj_prix,
                        date_adjudication=adj_date,
                        adresse=adj_adresse if adj_adresse else None,
                        ville=adj_ville if adj_ville else None,
                        type_bien=adj_type,
                        surface=adj_surface if adj_surface > 0 else None,
                        mise_a_prix=adj_mise_prix if adj_mise_prix > 0 else None,
                        tribunal=adj_tribunal,
                    )
                    if result_id:
                        st.success("Résultat enregistré !")
                        st.rerun()
                    else:
                        st.warning("Ce résultat existe peut-être déjà dans la base.")
                except Exception as e:
                    st.error(f"Erreur: {e}")
            else:
                st.error("Veuillez remplir au moins le code postal et le prix adjugé.")

    # Info about data sources
    st.markdown("---")
    st.markdown("""
    ### 📚 Sources de données

    Les résultats d'adjudication peuvent être trouvés sur :

    1. **Sites des cabinets d'avocats** (parfois publiés)
    2. **Licitor** - section "Résultats des adjudications" (souvent "inconnu")
    3. **Journaux d'annonces légales** (JAL)
    4. **Greffes des tribunaux** (sur demande)

    ⚠️ **Limitation** : La plupart des résultats d'adjudication ne sont pas publiés
    en ligne de manière systématique. Cette fonctionnalité se construit progressivement
    à partir des données disponibles.
    """)


def show_settings(db: Database):
    """Settings and administration"""
    st.subheader("⚙️ Paramètres et Administration")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🔄 Actions")

        if st.button("🔍 Lancer le scraping", use_container_width=True):
            with st.spinner("Scraping en cours..."):
                from main import run_scraping
                run_scraping()
                st.success("Scraping terminé!")
                st.rerun()

        if st.button("📊 Lancer l'analyse", use_container_width=True):
            with st.spinner("Analyse en cours..."):
                from main import run_analysis
                run_analysis()
                st.success("Analyse terminée!")
                st.rerun()

        if st.button("🔍 Rechercher sites avocats", use_container_width=True):
            with st.spinner("Recherche des sites..."):
                finder = get_lawyer_finder_cached()
                auctions = db.get_all_auctions(limit=100)
                finder.enrich_auctions(auctions)
                for a in auctions:
                    if a.avocat_site_web:
                        db.save_auction(a)
                st.success("Recherche terminée!")
                st.rerun()

    with col2:
        st.markdown("### 📊 Statistiques")
        stats = db.get_stats()

        st.markdown(f"**Total enchères:** {stats.get('total_auctions', 0)}")
        st.markdown(f"**À venir:** {stats.get('upcoming', 0)}")

        st.markdown("**Par source:**")
        for source, count in stats.get("by_source", {}).items():
            st.markdown(f"- {source}: {count}")

    st.markdown("---")
    st.markdown("### 📊 Méthodologie d'estimation des prix")

    st.markdown("""
    L'estimation des prix utilise une **approche multi-sources** qui combine 3 sources de données
    pour produire une estimation fiable avec un score de confiance.
    """)

    # Source 1: DVF
    with st.expander("🏛️ Source 1: DVF (Demandes de Valeurs Foncières) - Poids élevé", expanded=True):
        st.markdown("""
        **Description:**
        Base de données officielle du gouvernement français contenant toutes les transactions
        immobilières réalisées en France.

        **Source:**
        - [data.gouv.fr - DVF](https://www.data.gouv.fr/fr/datasets/demandes-de-valeurs-foncieres/)
        - [Visualisation officielle](https://app.dvf.etalab.gouv.fr/)

        **Méthodologie de calcul:**
        1. Recherche des transactions dans le **même code postal**
        2. Filtrage par **type de bien** (appartement, maison, etc.)
        3. Filtrage par **surface similaire** (±30% de la surface du bien analysé)
        4. Période: **24 derniers mois** de transactions
        5. Calcul de la **médiane** des prix/m² (plus robuste que la moyenne)
        6. Filtrage des outliers: prix/m² entre 500€ et 15 000€

        **Seuils de confiance:**
        - ≥20 transactions → 40 points de confiance
        - ≥10 transactions → 30 points
        - ≥5 transactions → 20 points
        - ≥3 transactions → 10 points (minimum requis)
        - <3 transactions → Données insuffisantes

        **Forces:** Données réelles de ventes effectives, source officielle et exhaustive

        **Limites:** Délai de publication (6 mois), peut manquer de données dans les petites communes
        """)

    # Source 2: Annonces en ligne
    with st.expander("🏘️ Source 2: Annonces en ligne - Poids moyen", expanded=True):
        st.markdown("""
        **Description:**
        Agrégation des prix demandés actuels sur les principales plateformes immobilières.

        **Sources interrogées:**
        - **LeBonCoin** (API) - Plus grand volume d'annonces
        - **SeLoger** (web scraping) - Référence professionnelle
        - **PAP.fr** (web scraping) - Particuliers à particuliers
        - **Bien'ici** (API) - Agrégateur multi-agences
        - **Logic-Immo** (web scraping) - Réseau d'agences

        **Méthodologie de calcul:**
        1. Recherche par **code postal** et **type de bien**
        2. Filtrage optionnel par **surface** (±30%)
        3. Collecte jusqu'à **35 annonces par source**
        4. Calcul de la **médiane** des prix/m²
        5. **Correction de -10%** sur les prix demandés
           (les prix affichés sont généralement 5-15% supérieurs aux prix de vente réels)
        6. Filtrage des outliers: prix/m² entre 500€ et 15 000€

        **Cache:** 24 heures pour éviter de surcharger les serveurs

        **Forces:** Données en temps réel, reflète le marché actuel

        **Limites:** Prix demandés ≠ prix de vente, nécessite une correction
        """)

    # Source 3: Indicateurs communaux
    with st.expander("📈 Source 3: Indicateurs Communaux - Poids faible", expanded=True):
        st.markdown("""
        **Description:**
        Statistiques agrégées par commune, publiées par le gouvernement.

        **Source:**
        - [Indicateurs immobiliers par commune 2014-2024](https://www.data.gouv.fr/fr/datasets/indicateurs-immobiliers-par-commune-et-par-annee-prix-et-volumes-sur-la-periode-2014-2024/)

        **Données utilisées:**
        - Prix moyen au m² par commune
        - Nombre de mutations (transactions)
        - Surface moyenne des biens vendus
        - Répartition maisons/appartements

        **Méthodologie:**
        1. Correspondance **code postal → code INSEE**
        2. Extraction des données de l'**année la plus récente** (2024)
        3. Utilisation du **prix/m² moyen** de la commune

        **Forces:** Vision globale du marché local, données officielles

        **Limites:** Moyenne générale (pas de distinction par quartier ou type précis),
        peut masquer des disparités locales
        """)

    # Calcul combiné
    st.markdown("---")
    st.markdown("### 🔬 Calcul de l'estimation finale")

    st.markdown("""
    **Moyenne pondérée par confiance:**

    L'estimation finale est calculée comme une **moyenne pondérée** où chaque source
    contribue selon son **score de confiance** (0-100):
    """)

    st.code("""
Prix final = Σ (prix_source × confiance_source) / Σ confiance_source

Confiance = f(nb_données, ancienneté, précision_géographique)
    """, language="text")

    st.markdown("""
    **Composantes du score de confiance (max 100 points):**

    | Critère | Points max | Détail |
    |---------|------------|--------|
    | Nombre de données | 40 pts | ≥20: 40pts, ≥10: 30pts, ≥5: 20pts, ≥3: 10pts |
    | Ancienneté | 30 pts | <6 mois: 30pts, <1 an: 20pts, <2 ans: 10pts |
    | Précision géo | 30 pts | Adresse exacte: 30pts, Commune: 20pts, Département: 10pts |

    **Accord entre sources:**

    Un indicateur d'accord mesure la cohérence des estimations:
    - **≥80%** → Sources en accord (estimation fiable)
    - **50-80%** → Accord modéré (à vérifier)
    - **<50%** → Sources en désaccord (prudence requise)

    *Calcul: 100 - (écart-type / moyenne × 200)*
    """)

    # Niveaux de fiabilité
    st.markdown("---")
    st.markdown("### 🎯 Niveaux de fiabilité")

    col_rel1, col_rel2 = st.columns(2)

    with col_rel1:
        st.markdown("""
        | Niveau | Score | Signification |
        |--------|-------|---------------|
        | 🟢 **Élevé** | ≥70% + 2 sources | Estimation très fiable |
        | 🟡 **Moyen** | ≥40% | Estimation indicative |
        | 🔴 **Faible** | >0% | À prendre avec précaution |
        | ⚪ **Insuffisant** | 0% | Pas assez de données |
        """)

    with col_rel2:
        st.markdown("""
        **Recommandations par niveau:**

        - 🟢 **Élevé:** Vous pouvez vous fier à cette estimation
        - 🟡 **Moyen:** Croisez avec vos propres recherches
        - 🔴 **Faible:** Estimation approximative uniquement
        - ⚪ **Insuffisant:** Faites votre propre analyse
        """)

    # Calcul de la décote
    st.markdown("---")
    st.markdown("### 📉 Calcul de la décote et du score d'opportunité")

    st.markdown("""
    **Décote vs marché:**
    """)
    st.code("""
Décote (%) = (Valeur marché - Mise à prix) / Valeur marché × 100

Exemple: Bien estimé à 200 000€, mise à prix 140 000€
Décote = (200000 - 140000) / 200000 × 100 = 30%
    """, language="text")

    st.markdown("""
    **Interprétation:**

    | Décote | Évaluation | Recommandation |
    |--------|------------|----------------|
    | ≥40% | 🌟 Exceptionnel | Opportunité rare, agir vite |
    | 30-40% | ⭐ Bonne opportunité | Très intéressant |
    | 20-30% | ✨ Bonne affaire | Intéressant si bon état |
    | 0-20% | 📊 Prix marché | Normal pour une enchère |
    | <0% | ⚠️ Surévalué | Mise à prix trop élevée |

    ⚠️ **Attention:** Une décote élevée peut aussi signifier:
    - Bien nécessitant des travaux importants
    - Occupation (locataire, squatteur)
    - Charges de copropriété élevées
    - Servitudes ou problèmes juridiques

    **Consultez toujours le cahier des charges avant d'enchérir!**
    """)

    st.markdown("---")
    st.markdown("### ℹ️ Automatisation")
    st.markdown("""
    - Scraping quotidien à 6h00
    - Mise à jour DVF hebdomadaire (dimanche 3h00)

    **Commandes:**
    ```bash
    python scheduler.py          # Lancer le scheduler
    python scheduler.py --once   # Exécution unique
    python main.py scrape        # Scraping manuel
    python main.py analyze       # Analyse manuelle
    ```
    """)


# ==================== HELPER FUNCTIONS ====================

def build_dvf_link(auction) -> str:
    """Build link to official DVF data source for price verification"""
    # The official DVF app doesn't support URL parameters for direct commune access
    # We link to the main app where users can search manually
    return "https://app.dvf.etalab.gouv.fr/"


def create_auctions_dataframe(auctions) -> pd.DataFrame:
    """Create DataFrame for auction table"""
    data = []
    for a in auctions:
        # Calculate price per m²
        prix_m2_enchere = None
        if a.mise_a_prix and a.surface and a.surface > 0:
            prix_m2_enchere = a.mise_a_prix / a.surface

        # Build mailto link
        mailto_link = build_email_link(a)

        # Build DVF source link
        dvf_link = build_dvf_link(a)

        data.append({
            "Date": a.date_vente,
            "Ville": a.ville,
            "Type": a.type_bien.value if a.type_bien else "",
            "Surface": a.surface,
            "Mise à prix": a.mise_a_prix,
            "€/m² enchère": prix_m2_enchere,
            "€/m² marché": a.prix_m2_marche,
            "📊 DVF": dvf_link,
            "Décote": a.decote_pourcentage,
            "Score": a.score_opportunite,
            "Avocat": a.avocat_nom,
            "Téléphone": a.avocat_telephone,
            "📧 Demander docs": mailto_link,
            "🌐 Site": a.avocat_site_web,
            "Annonce": a.url,
        })

    return pd.DataFrame(data)


def build_email_link(auction) -> str:
    """Build a complete mailto link with pre-filled content"""
    if not auction.avocat_email:
        return None

    # Format values
    date_vente = auction.date_vente.strftime('%d/%m/%Y') if auction.date_vente else "Non précisée"
    mise_prix = f"{auction.mise_a_prix:,.0f} €".replace(",", " ") if auction.mise_a_prix else "Non précisée"
    surface = f"{auction.surface} m²" if auction.surface else "Non précisée"
    type_bien = auction.type_bien.value if auction.type_bien else "Bien immobilier"

    # Dates de visite
    visites = ""
    if auction.dates_visite:
        visites = "\n- Dates de visite : " + ", ".join(d.strftime("%d/%m/%Y à %Hh%M") for d in auction.dates_visite)

    subject = f"Demande de cahier des charges - {auction.ville} - Vente du {date_vente}"

    body = f"""Maître,

Je souhaiterais obtenir le cahier des charges ainsi que l'ensemble des documents officiels concernant la vente aux enchères suivante :

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📍 INFORMATIONS DU BIEN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Adresse : {auction.adresse or 'Non précisée'}, {auction.ville}
- Type de bien : {type_bien}
- Surface : {surface}
- Mise à prix : {mise_prix}

📅 DATES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Date de vente : {date_vente}
- Heure : {auction.heure_vente or 'Non précisée'}{visites}

🏛️ TRIBUNAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- {auction.tribunal}

📋 DOCUMENTS DEMANDÉS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Cahier des charges
- Procès-verbal descriptif
- Diagnostics techniques
- État des inscriptions hypothécaires
- Tout autre document utile à l'examen du bien

Merci de me faire parvenir ces documents par retour de mail ou de m'indiquer les modalités pour les consulter.

Cordialement,

[Votre nom]
[Votre téléphone]
[Votre email]"""

    return f"mailto:{auction.avocat_email}?subject={quote(subject)}&body={quote(body)}"


def display_auction_row(auction):
    """Display a compact auction row"""
    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])

    with col1:
        date_str = auction.date_vente.strftime("%d/%m") if auction.date_vente else "?"
        st.markdown(f"**{date_str}** • {auction.ville} • {auction.type_bien.value if auction.type_bien else 'Bien'}")

    with col2:
        if auction.surface:
            st.markdown(f"{auction.surface:.0f} m²")

    with col3:
        if auction.mise_a_prix:
            st.markdown(f"**{auction.mise_a_prix:,.0f} €**")

    with col4:
        if auction.decote_pourcentage:
            color = "green" if auction.decote_pourcentage >= 30 else "orange" if auction.decote_pourcentage >= 20 else "gray"
            st.markdown(f"<span style='color:{color}'>-{auction.decote_pourcentage:.0f}%</span>", unsafe_allow_html=True)


def display_opportunity_card(auction):
    """Display opportunity summary card"""
    with st.container():
        score = auction.score_opportunite or 0
        color = "#10b981" if score >= 70 else "#f59e0b" if score >= 50 else "#6b7280"

        st.markdown(f"""
        <div style='background:rgba(30, 58, 95, 0.6); padding:0.8rem; border-radius:8px; margin-bottom:0.5rem; border-left:4px solid {color}'>
            <strong style='color:#f0f4f8'>{auction.ville}</strong><br/>
            <small style='color:#a0b4c8'>{auction.type_bien.value if auction.type_bien else 'Bien'} • {auction.surface or '?'}m²</small><br/>
            <strong style='color:{color}'>{auction.mise_a_prix:,.0f}€</strong> • <span style='color:#f0f4f8'>Score: {score:.0f}</span>
        </div>
        """, unsafe_allow_html=True)


def display_nouveaute_card(auction):
    """Display a card for newly added auctions"""
    type_bien = auction.type_bien.value if auction.type_bien else "Bien"
    date_vente = auction.date_vente.strftime("%d/%m/%Y") if auction.date_vente else "Date non précisée"
    mise_prix = f"{auction.mise_a_prix:,.0f}€".replace(",", " ") if auction.mise_a_prix else "Prix non précisé"
    surface = f"{auction.surface:.0f}m²" if auction.surface else "?"
    decote = auction.decote_pourcentage

    # Badge color based on decote
    if decote and decote >= 30:
        badge_color = "#10b981"
        badge_text = f"🔥 -{decote:.0f}%"
    elif decote and decote >= 20:
        badge_color = "#f59e0b"
        badge_text = f"⭐ -{decote:.0f}%"
    else:
        badge_color = "#3b82f6"
        badge_text = "🆕 Nouveau"

    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])

    with col1:
        st.markdown(f"""
        <div style='display:flex; align-items:center; gap:0.5rem'>
            <span style='background:{badge_color}; color:white; padding:0.2rem 0.5rem; border-radius:12px; font-size:0.75em; font-weight:600'>{badge_text}</span>
            <strong style='color:#f0f4f8'>{type_bien.capitalize()} à {auction.ville}</strong>
        </div>
        <small style='color:#a0b4c8'>{auction.adresse or ''}</small>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"**{surface}**")

    with col3:
        st.markdown(f"**{mise_prix}**")

    with col4:
        st.markdown(f"📅 {date_vente}")


def display_full_auction_card(auction):
    """Display full auction card with all details"""
    with st.expander(
        f"📍 {auction.ville} • {auction.type_bien.value if auction.type_bien else 'Bien'} {auction.surface or '?'}m² • {auction.mise_a_prix:,.0f}€" if auction.mise_a_prix else f"📍 {auction.ville}",
        expanded=False
    ):
        col1, col2, col3 = st.columns([2, 1, 1])

        with col1:
            st.markdown("**📍 Localisation**")
            st.markdown(f"- Adresse : {auction.adresse or 'Non renseignée'}")
            st.markdown(f"- Ville : {auction.ville}")
            st.markdown(f"- Code postal : {auction.code_postal or 'N/A'}")

            st.markdown("**🏠 Caractéristiques**")
            st.markdown(f"- Type : {auction.type_bien.value if auction.type_bien else 'Non précisé'}")
            st.markdown(f"- Surface : {auction.surface or '?'} m²")
            st.markdown(f"- Pièces : {auction.nb_pieces or '?'}")

        with col2:
            st.markdown("**💰 Prix**")
            st.metric("Mise à prix", f"{auction.mise_a_prix:,.0f} €" if auction.mise_a_prix else "?")
            if auction.prix_marche_estime:
                st.metric("Valeur marché", f"{auction.prix_marche_estime:,.0f} €")
            if auction.decote_pourcentage:
                st.metric("Décote", f"{auction.decote_pourcentage:.0f}%")

        with col3:
            st.markdown("**📊 Analyse**")
            st.metric("Score", f"{auction.score_opportunite:.0f}/100" if auction.score_opportunite else "?")

            if auction.prix_m2_marche and auction.surface and auction.mise_a_prix:
                prix_m2_enchere = auction.mise_a_prix / auction.surface
                st.markdown(f"€/m² enchère : **{prix_m2_enchere:.0f}€**")
                st.markdown(f"€/m² marché : **{auction.prix_m2_marche:.0f}€**")

        st.markdown("---")

        # Dates
        col_date1, col_date2 = st.columns(2)
        with col_date1:
            st.markdown("**📅 Dates**")
            if auction.date_vente:
                st.markdown(f"- Vente : **{auction.date_vente.strftime('%d/%m/%Y')}** à {auction.heure_vente or '?'}")
            if auction.dates_visite:
                visites = ", ".join(d.strftime("%d/%m/%Y %Hh%M") for d in auction.dates_visite)
                st.markdown(f"- Visites : {visites}")
            st.markdown(f"- Tribunal : {auction.tribunal}")

        with col_date2:
            st.markdown("**👨‍⚖️ Avocat**")
            if auction.avocat_nom:
                st.markdown(f"- **Me {auction.avocat_nom}**")
            if auction.avocat_cabinet:
                st.markdown(f"- Cabinet : {auction.avocat_cabinet}")
            if auction.avocat_telephone:
                st.markdown(f"- 📞 {auction.avocat_telephone}")
            if auction.avocat_email:
                st.markdown(f"- 📧 {auction.avocat_email}")

            # Check lawyers catalog for known website
            lawyer_info = find_lawyer_info(auction.avocat_nom, auction.avocat_cabinet)
            if lawyer_info and lawyer_info.get("page_encheres"):
                st.markdown(f"- 🌐 [Page enchères]({lawyer_info['page_encheres']})")

        # Action buttons
        st.markdown("---")
        btn_col1, btn_col2, btn_col3 = st.columns(3)

        with btn_col1:
            if auction.url:
                st.link_button("🔗 Voir l'annonce", auction.url, use_container_width=True)

        with btn_col2:
            if auction.avocat_email:
                mailto = build_email_link(auction)
                st.link_button("📧 Demander les documents", mailto, use_container_width=True)

        with btn_col3:
            # Use catalog if avocat_site_web is empty
            site_url = auction.avocat_site_web or get_encheres_url(auction.avocat_nom, auction.avocat_cabinet)
            if site_url:
                st.link_button("🌐 Site avocat", site_url, use_container_width=True)


def geocode_address(address: str, city: str, postal_code: str) -> tuple:
    """Geocode an address using French government API (most precise) with Nominatim fallback"""
    import requests
    import re

    # Clean and normalize address
    address_clean = (address or "").strip()
    city_clean = (city or "").strip()
    postal_code_clean = (postal_code or "").strip()

    # Strategy 1: French Government API (api-adresse.data.gouv.fr) - most precise for France
    if address_clean or city_clean:
        try:
            # Build query with address components
            query_parts = []
            if address_clean:
                query_parts.append(address_clean)
            if city_clean:
                query_parts.append(city_clean)

            query = " ".join(query_parts)

            params = {
                "q": query,
                "limit": 1,
            }
            # Add postcode filter for more precision
            if postal_code_clean and postal_code_clean.isdigit():
                params["postcode"] = postal_code_clean

            response = requests.get(
                "https://api-adresse.data.gouv.fr/search/",
                params=params,
                headers={"User-Agent": "ImmoAgent/1.0"},
                timeout=5
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("features") and len(data["features"]) > 0:
                    coords = data["features"][0]["geometry"]["coordinates"]
                    # GeoJSON format: [lon, lat]
                    return float(coords[1]), float(coords[0])
        except Exception:
            pass

    # Strategy 2: Try with just postcode and city for broader match
    if postal_code_clean and city_clean:
        try:
            response = requests.get(
                "https://api-adresse.data.gouv.fr/search/",
                params={
                    "q": city_clean,
                    "postcode": postal_code_clean,
                    "type": "municipality",
                    "limit": 1,
                },
                headers={"User-Agent": "ImmoAgent/1.0"},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("features") and len(data["features"]) > 0:
                    coords = data["features"][0]["geometry"]["coordinates"]
                    return float(coords[1]), float(coords[0])
        except Exception:
            pass

    # Strategy 3: Nominatim fallback
    full_query = f"{address_clean}, {postal_code_clean} {city_clean}, France" if address_clean else f"{postal_code_clean} {city_clean}, France"
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": full_query,
                "format": "json",
                "limit": 1,
                "countrycodes": "fr"
            },
            headers={"User-Agent": "ImmoAgent/1.0"},
            timeout=5
        )
        if response.status_code == 200 and response.json():
            data = response.json()[0]
            return float(data["lat"]), float(data["lon"])
    except Exception:
        pass

    # Strategy 4: Nominatim structured search
    if city_clean:
        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "city": city_clean,
                    "postalcode": postal_code_clean,
                    "country": "France",
                    "format": "json",
                    "limit": 1,
                },
                headers={"User-Agent": "ImmoAgent/1.0"},
                timeout=5
            )
            if response.status_code == 200 and response.json():
                data = response.json()[0]
                return float(data["lat"]), float(data["lon"])
        except Exception:
            pass

    # Fallback coordinates for major cities
    city_coords = {
        "marseille": (43.2965, 5.3698),
        "aix-en-provence": (43.5297, 5.4474),
        "toulon": (43.1242, 5.9280),
        "aubagne": (43.2927, 5.5708),
        "hyeres": (43.1204, 6.1286),
        "la ciotat": (43.1748, 5.6047),
        "martigues": (43.4053, 5.0476),
        "frejus": (43.4330, 6.7370),
        "draguignan": (43.5366, 6.4647),
        "la seyne-sur-mer": (43.0833, 5.8833),
        "salon-de-provence": (43.6400, 5.0970),
        "istres": (43.5150, 4.9870),
        "vitrolles": (43.4550, 5.2480),
        "arles": (43.6770, 4.6300),
        "tarascon": (43.8060, 4.6600),
        "gardanne": (43.4540, 5.4690),
        "miramas": (43.5850, 5.0010),
        "saint-raphael": (43.4250, 6.7680),
        "six-fours-les-plages": (43.0930, 5.8200),
        "bandol": (43.1350, 5.7520),
        "sanary-sur-mer": (43.1190, 5.8010),
        "ollioules": (43.1410, 5.8520),
    }
    city_lower = city_clean.lower() if city_clean else ""
    for city_name, coords in city_coords.items():
        if city_name in city_lower or city_lower in city_name:
            return coords

    return None, None


def display_property_analysis(auction):
    """Display detailed property analysis with multi-source pricing"""
    import folium
    from streamlit_folium import st_folium

    # ==================== 1. PROPERTY INFO HEADER ====================
    st.markdown("---")

    # Property title with key info
    type_bien = auction.type_bien.value if auction.type_bien else "Bien"
    occupation_badge = ""
    occupation = getattr(auction, 'occupation', '') or ''
    if occupation:
        occ_color = "#10b981" if "libre" in occupation.lower() else "#ef4444"
        occupation_badge = f"<span style='background:{occ_color}; color:white; padding:0.2rem 0.6rem; border-radius:12px; font-size:0.85em; margin-left:0.5rem'>{occupation}</span>"

    st.markdown(f"""
    <div class='property-info-card'>
        <h2 style='margin:0; color:#1f2937'>🏠 {type_bien.capitalize()} à {auction.ville}{occupation_badge}</h2>
        <p style='color:#6b7280; margin:0.5rem 0 0 0; font-size:1.1rem'>{auction.adresse or 'Adresse non précisée'}</p>
    </div>
    """, unsafe_allow_html=True)

    # ==================== TOP ACTION BUTTONS ====================
    top_btn1, top_btn2, top_btn3 = st.columns(3)
    with top_btn1:
        if auction.url:
            st.link_button("🔗 Voir l'annonce source", auction.url, use_container_width=True)
    with top_btn2:
        if auction.pv_url:
            st.link_button("📄 PV Descriptif", auction.pv_url, use_container_width=True)
    with top_btn3:
        lawyer_info = find_lawyer_info(auction.avocat_nom, auction.avocat_cabinet)
        site_url = auction.avocat_site_web or (lawyer_info.get("page_encheres") if lawyer_info else None)
        if site_url:
            st.link_button("👨‍⚖️ Site avocat", site_url, use_container_width=True)

    # ==================== PHOTOS GALLERY ====================
    photos = getattr(auction, 'photos', []) or []
    if photos:
        st.markdown("### 📷 Photos du bien")
        # Display photos in a grid
        photo_cols = st.columns(min(4, len(photos)))
        for idx, photo_url in enumerate(photos[:8]):  # Show first 8 photos
            with photo_cols[idx % 4]:
                st.image(photo_url, use_container_width=True)

        if len(photos) > 8:
            st.caption(f"+ {len(photos) - 8} autres photos disponibles")

        st.markdown("---")

    # ==================== 2. KEY INFO + MAP ROW ====================
    col_info, col_map = st.columns([1, 1])

    with col_info:
        # Visit dates prominently displayed
        st.markdown("### 📅 Dates importantes")

        if auction.dates_visite:
            st.markdown("**Visites programmées :**")
            for visite in auction.dates_visite:
                st.markdown(f"""
                <span class='visit-date-badge'>📍 {visite.strftime('%A %d/%m/%Y à %Hh%M')}</span>
                """, unsafe_allow_html=True)
        else:
            st.info("Dates de visite non communiquées - contacter l'avocat")

        if auction.date_vente:
            st.markdown(f"**Vente aux enchères :** {auction.date_vente.strftime('%A %d/%m/%Y')} à {auction.heure_vente or '?'}")
            st.markdown(f"**Tribunal :** {auction.tribunal}")

        st.markdown("---")

        # Property characteristics
        st.markdown("### 🏗️ Caractéristiques")
        char_col1, char_col2 = st.columns(2)
        cadastre = getattr(auction, 'cadastre', '') or ''
        with char_col1:
            st.markdown(f"**Type :** {type_bien}")
            st.markdown(f"**Surface :** {auction.surface or '?'} m²")
            if cadastre:
                st.markdown(f"**Cadastre :** {cadastre}")
        with char_col2:
            st.markdown(f"**Pièces :** {auction.nb_pieces or '?'}")
            st.markdown(f"**Code postal :** {auction.code_postal or 'N/A'}")
            if occupation:
                st.markdown(f"**Occupation :** {occupation}")

    with col_map:
        # Interactive map
        st.markdown("### 📍 Localisation")
        lat, lon = geocode_address(
            auction.adresse or "",
            auction.ville or "",
            auction.code_postal or ""
        )

        if lat and lon:
            # Google Maps URL
            address_query = f"{auction.adresse or ''}, {auction.code_postal or ''} {auction.ville or ''}".strip()
            google_maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
            google_maps_directions = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"

            # Create map with clickable marker
            m = folium.Map(location=[lat, lon], zoom_start=15, tiles="OpenStreetMap")

            # Popup with Google Maps link
            popup_html = f"""
            <div style="font-family: Arial, sans-serif; min-width: 200px;">
                <b>{auction.adresse or auction.ville}</b><br/>
                <span style="color: #666;">{type_bien} - {auction.surface or '?'}m²</span><br/>
                <div style="margin-top: 8px;">
                    <a href="{google_maps_url}" target="_blank"
                       style="display: inline-block; padding: 5px 10px; background: #4285f4; color: white;
                              text-decoration: none; border-radius: 4px; margin-right: 5px;">
                        📍 Google Maps
                    </a>
                    <a href="{google_maps_directions}" target="_blank"
                       style="display: inline-block; padding: 5px 10px; background: #34a853; color: white;
                              text-decoration: none; border-radius: 4px;">
                        🚗 Itinéraire
                    </a>
                </div>
            </div>
            """

            folium.Marker(
                [lat, lon],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"Cliquez pour voir les options",
                icon=folium.Icon(color="red", icon="home", prefix="fa")
            ).add_to(m)
            st_folium(m, width=400, height=300, returned_objects=[])

            # Direct Google Maps buttons below map
            gmap_col1, gmap_col2 = st.columns(2)
            with gmap_col1:
                st.link_button("📍 Ouvrir Google Maps", google_maps_url, use_container_width=True)
            with gmap_col2:
                st.link_button("🚗 Itinéraire", google_maps_directions, use_container_width=True)
        else:
            st.warning("Localisation approximative non disponible")


    # ==================== DETAILED DESCRIPTION ====================
    description_detaillee = getattr(auction, 'description_detaillee', '') or ''
    if description_detaillee:
        st.markdown("---")
        st.markdown("### 📝 Description détaillée")
        # Format description with line breaks
        desc_formatted = description_detaillee.replace("\n", "<br/>")
        st.markdown(f"""
        <div style='background:rgba(30, 58, 95, 0.4); padding:1rem; border-radius:8px; border-left:4px solid #7dd3fc; line-height:1.6'>
            {desc_formatted}
        </div>
        """, unsafe_allow_html=True)

    # ==================== DOCUMENTS SECTION ====================
    documents = getattr(auction, 'documents', []) or []
    pv_url = getattr(auction, 'pv_url', None)

    # Show documents section if we have documents OR pv_url
    if documents or pv_url:
        st.markdown("---")
        st.markdown("### 📄 Documents officiels")
        st.caption("Cahier des charges, PV, diagnostics et autres documents disponibles")

        # Build document list including PV if not already in documents
        all_docs = list(documents)
        if pv_url:
            # Check if PV not already in documents
            pv_exists = any('pv' in str(d.get('url', '')).lower() or 'pv' in str(d.get('nom', '')).lower() for d in all_docs)
            if not pv_exists:
                all_docs.insert(0, {'nom': 'PV Descriptif', 'url': pv_url, 'type': 'Procès-verbal de description'})

        doc_cols = st.columns(min(4, max(1, len(all_docs))))
        doc_icons = {
            "Cahier des conditions de vente": "📖",
            "Procès-verbal de description": "📋",
            "Diagnostics immobiliers": "🔍",
            "Avis de vente": "📢",
            "Jugement": "⚖️",
            "Rapport d'expertise": "📊",
            "Autre document": "📄"
        }

        for idx, doc in enumerate(all_docs[:8]):
            with doc_cols[idx % 4]:
                icon = doc_icons.get(doc.get('type', ''), '📄')
                doc_name = doc.get('nom', doc.get('name', 'Document'))[:30]
                doc_url = doc.get('url', '')
                st.markdown(f"""
                <div style='background:rgba(30, 58, 95, 0.5); padding:0.8rem; border-radius:8px; text-align:center; margin-bottom:0.5rem'>
                    <span style='font-size:1.5rem'>{icon}</span><br/>
                    <small>{doc_name}</small>
                </div>
                """, unsafe_allow_html=True)
                if doc_url:
                    st.link_button("📥 Télécharger", doc_url, use_container_width=True)

    # ==================== 3. PRICE METRICS ====================
    st.markdown("---")
    st.markdown("### 💰 Prix et Valorisation")

    # Calculate price per m²
    prix_m2_enchere = None
    if auction.mise_a_prix and auction.surface and auction.surface > 0:
        prix_m2_enchere = auction.mise_a_prix / auction.surface

    # Run multi-source analysis
    analyzer = get_multi_source_analyzer()
    analysis = analyzer.analyze(
        code_postal=auction.code_postal or "",
        ville=auction.ville or "",
        type_bien=auction.type_bien.value if auction.type_bien else "appartement",
        surface=auction.surface,
        mise_a_prix=auction.mise_a_prix,
    )

    # Price metrics in clear columns
    price_col1, price_col2, price_col3, price_col4, price_col5 = st.columns(5)

    with price_col1:
        st.metric(
            "💵 Mise à prix",
            f"{auction.mise_a_prix:,.0f} €".replace(",", " ") if auction.mise_a_prix else "?",
        )
    with price_col2:
        st.metric(
            "📐 Prix/m² enchère",
            f"{prix_m2_enchere:,.0f} €/m²".replace(",", " ") if prix_m2_enchere else "?",
            help="Mise à prix divisée par la surface"
        )
    with price_col3:
        st.metric(
            "📊 Prix/m² marché",
            f"{analysis.prix_m2_recommended:,.0f} €/m²".replace(",", " ") if analysis.prix_m2_recommended else "?",
            help="Estimation multi-sources"
        )
    with price_col4:
        st.metric(
            "🏠 Valeur marché",
            f"{analysis.prix_total_estimated:,.0f} €".replace(",", " ") if analysis.prix_total_estimated else "?",
        )
    with price_col5:
        decote = analysis.decote_vs_market
        if decote:
            color = "normal" if decote >= 20 else "off" if decote < 0 else "normal"
            st.metric(
                "📉 Décote",
                f"{decote:.0f}%",
                delta=f"{decote:.0f}% sous le marché" if decote > 0 else f"{abs(decote):.0f}% au-dessus",
                delta_color="normal" if decote > 0 else "inverse"
            )
        else:
            st.metric("📉 Décote", "?")

    # ==================== 4. RECOMMENDATION ====================
    st.markdown("---")

    rec_col, sources_col = st.columns([1, 2])

    with rec_col:
        st.markdown("### 💡 Recommandation")
        if analysis.decote_vs_market:
            if analysis.decote_vs_market >= 40:
                st.success("🌟 OPPORTUNITÉ EXCEPTIONNELLE")
                st.markdown(f"Décote de **{analysis.decote_vs_market:.0f}%** vs marché")
            elif analysis.decote_vs_market >= 30:
                st.success("⭐ BONNE OPPORTUNITÉ")
                st.markdown(f"Décote de **{analysis.decote_vs_market:.0f}%** vs marché")
            elif analysis.decote_vs_market >= 20:
                st.info("✨ BONNE AFFAIRE")
                st.markdown(f"Décote de **{analysis.decote_vs_market:.0f}%** vs marché")
            elif analysis.decote_vs_market >= 0:
                st.warning("📊 PRIX MARCHÉ")
                st.markdown("Proche de la valeur marché")
            else:
                st.error("⚠️ SURÉVALUÉ")
                st.markdown(f"**{abs(analysis.decote_vs_market):.0f}%** au-dessus du marché")

        # Reliability indicator
        reliability_colors = {
            "high": "🟢", "medium": "🟡", "low": "🔴", "insufficient": "⚪"
        }
        rel_icon = reliability_colors.get(analysis.reliability.value, "⚪")
        st.markdown(f"**Fiabilité estimation:** {rel_icon} {analysis.reliability_score:.0f}%")

        # Warnings
        if analysis.warnings:
            for w in analysis.warnings:
                st.caption(f"⚠️ {w}")

    with sources_col:
        st.markdown("### 📊 Détail des sources")
        src_col1, src_col2, src_col3 = st.columns(3)

        with src_col1:
            if analysis.estimate.dvf_estimate:
                st.markdown("**DVF (transactions)**")
                st.markdown(f"## {analysis.estimate.dvf_estimate:,.0f} €/m²")
                st.caption("Ventes officielles")
            else:
                st.markdown("**DVF**")
                st.caption("Données insuffisantes")

        with src_col2:
            if analysis.estimate.listings_estimate:
                st.markdown("**Annonces en ligne**")
                st.markdown(f"## {analysis.estimate.listings_estimate:,.0f} €/m²")
                st.caption("Prix demandés -10%")
            else:
                st.markdown("**Annonces**")
                st.caption("Données insuffisantes")

        with src_col3:
            if analysis.estimate.commune_estimate:
                st.markdown("**Moyenne commune**")
                st.markdown(f"## {analysis.estimate.commune_estimate:,.0f} €/m²")
                st.caption("Statistiques 2024")
            else:
                st.markdown("**Commune**")
                st.caption("Données insuffisantes")

        # Agreement indicator
        if analysis.estimate.sources_agreement:
            agreement = analysis.estimate.sources_agreement
            if agreement >= 80:
                st.success(f"✓ Sources en accord ({agreement:.0f}%)")
            elif agreement >= 50:
                st.warning(f"~ Accord modéré ({agreement:.0f}%)")
            else:
                st.error(f"✗ Sources en désaccord ({agreement:.0f}%)")

        # MeilleursAgents link in sources section
        import urllib.parse
        address_parts = []
        if auction.adresse:
            address_parts.append(auction.adresse)
        if auction.ville:
            address_parts.append(auction.ville)
        if auction.code_postal:
            address_parts.append(auction.code_postal)

        if address_parts:
            address_query = urllib.parse.quote(" ".join(address_parts))
            meilleursagents_url = f"https://www.meilleursagents.com/prix-immobilier/?q={address_query}"
            st.link_button("🏠 Comparer sur MeilleursAgents", meilleursagents_url, use_container_width=True)

    st.markdown("---")

    # Listings section - show similar properties with clickable links
    source_details = analyzer.get_source_details(analysis)
    listings_details = source_details.get('listings')

    if listings_details and listings_details.get('comparables'):
        st.markdown("### 🏘️ Annonces similaires en ligne")
        st.caption("Prix demandés actuels via LeBonCoin, SeLoger, PAP, Bien'ici, Logic-Immo")

        listings = listings_details['comparables'][:8]  # Show up to 8

        # Source colors
        source_colors = {
            'LeBonCoin': '#f56b2a',  # Orange LeBonCoin
            'SeLoger': '#e4002b',    # Red SeLoger
            'PAP': '#0066cc',        # Blue PAP
            "Bien'ici": '#00b3a4',   # Teal Bien'ici
            'Logic-Immo': '#1a1a1a', # Black Logic-Immo
        }

        # Display in 2 columns
        cols = st.columns(2)
        for i, listing in enumerate(listings):
            with cols[i % 2]:
                prix = listing.get('prix', 0)
                surface = listing.get('surface', 0)
                prix_m2 = listing.get('prix_m2', 0)
                titre = listing.get('titre', 'Annonce')[:45]
                url = listing.get('url', '')
                source = listing.get('source', 'Annonce')
                source_color = source_colors.get(source, '#6b7280')

                st.markdown(f"""
                <div style='background:rgba(30, 58, 95, 0.6); padding:0.6rem; border-radius:6px; margin-bottom:0.5rem; border-left:3px solid {source_color}'>
                    <span style='background:{source_color}; color:white; padding:0.15rem 0.4rem; border-radius:4px; font-size:0.7em; font-weight:500'>{source}</span><br/>
                    <strong style='color:#f0f4f8'>{titre}...</strong><br/>
                    <span style='color:{source_color}; font-size:1.1em; font-weight:600'>{prix:,.0f}€</span> • <span style='color:#a0b4c8'>{surface:.0f}m² • {prix_m2:,.0f}€/m²</span>
                </div>
                """, unsafe_allow_html=True)
                if url:
                    st.link_button("🔗 Voir l'annonce", url, use_container_width=True)

        st.caption(f"💡 Prix affichés = prix demandés. L'estimation de marché applique -10% de correction.")
        st.markdown("---")

    # Detailed sources section (expandable)
    with st.expander("📋 Détails des sources DVF et commune"):
        for source_type, details in source_details.items():
            if source_type == 'listings':
                continue  # Already shown above

            st.markdown(f"#### {details['name']}")
            col_a, col_b = st.columns(2)

            with col_a:
                st.markdown(f"- Prix/m²: **{details['prix_m2']:,.0f}€**" if details['prix_m2'] else "- Prix/m²: N/A")
                st.markdown(f"- Données: {details['nb_data_points']}")
                st.markdown(f"- Confiance: {details['confidence']:.0f}%")

            with col_b:
                if details.get('source_url'):
                    st.link_button("🔗 Voir la source", details['source_url'], use_container_width=True)
                st.caption(details.get('notes', ''))

            # Show comparables if available (DVF transactions)
            if details.get('comparables'):
                st.markdown("**Transactions comparables:**")
                comps_df = pd.DataFrame(details['comparables'][:5])
                if not comps_df.empty:
                    # Format columns for display
                    display_cols = [c for c in comps_df.columns if c not in ['url']]
                    st.dataframe(comps_df[display_cols], hide_index=True, use_container_width=True)

            st.markdown("---")

    # Contact section
    st.markdown("### 👨‍⚖️ Contact")
    contact_col1, contact_col2, contact_col3 = st.columns(3)

    with contact_col1:
        if auction.avocat_nom:
            st.markdown(f"**Me {auction.avocat_nom}**")
        if auction.avocat_telephone:
            st.markdown(f"📞 {auction.avocat_telephone}")
        if auction.avocat_email:
            st.markdown(f"📧 {auction.avocat_email}")

    with contact_col2:
        if auction.avocat_email:
            mailto = build_email_link(auction)
            st.link_button("📧 Demander les documents", mailto, use_container_width=True, type="primary")

    with contact_col3:
        if auction.url:
            st.link_button("🔗 Voir l'annonce", auction.url, use_container_width=True)
        if auction.avocat_site_web:
            st.link_button("🌐 Site avocat", auction.avocat_site_web, use_container_width=True)


if __name__ == "__main__":
    main()
