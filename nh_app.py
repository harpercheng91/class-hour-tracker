import streamlit as st
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime

# ========== Page config ==========
st.set_page_config(page_title="Class Hours Tracker", page_icon="📚", layout="wide")
st.title("📚 Class Hours & Payment Tracker")

# ========== Settings persistence ==========
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nh_setting.json")

DEFAULT_SETTINGS = {
    "has_base_salary": "No",
    "base_salary": 0.0,
    "has_obligation": "No",
    "obligation_hours": 20.0,
    "flat_rate": 200.0,
    "rules": [
        {"upper": 10.0, "rate": 200.0},
        {"upper": None, "rate": 250.0},
    ],
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            return {**DEFAULT_SETTINGS, **saved}
        except Exception:
            return DEFAULT_SETTINGS.copy()
    return DEFAULT_SETTINGS.copy()

def _file_mtime():
    try:
        return os.path.getmtime(SETTINGS_FILE)
    except OSError:
        return None

# On every run: re-read the JSON if it changed on disk.
_disk_mtime = _file_mtime()

if "settings_loaded" not in st.session_state:
    st.session_state.settings_loaded = False
    st.session_state._settings_mtime = None

if (not st.session_state.settings_loaded) or (st.session_state._settings_mtime != _disk_mtime):
    saved = load_settings()
    st.session_state.has_base_salary = saved["has_base_salary"]
    st.session_state.base_salary = saved["base_salary"]
    st.session_state.has_obligation = saved["has_obligation"]
    st.session_state.obligation_hours = saved["obligation_hours"]
    st.session_state.flat_rate = saved["flat_rate"]
    st.session_state.rules = saved["rules"]
    st.session_state.settings_loaded = True
    st.session_state._settings_mtime = _disk_mtime

def save_settings(has_base_salary, base_salary, has_obligation,
                  obligation_hours, flat_rate, rules):
    data = {
        "has_base_salary": has_base_salary,
        "base_salary": base_salary,
        "has_obligation": has_obligation,
        "obligation_hours": obligation_hours,
        "flat_rate": flat_rate,
        "rules": rules,
    }
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        st.session_state._settings_mtime = os.path.getmtime(SETTINGS_FILE)
    except OSError:
        st.session_state._settings_mtime = None

# ========== Data loading ==========
@st.cache_data
def load_data(file):
    df = pd.read_excel(file, sheet_name=None,
                       dtype={'class_start_time': str, 'class_end_time': str})
    all_df = pd.concat(df.values(), ignore_index=True)

    all_df['date'] = all_df['date'].ffill()
    all_df['date'] = pd.to_datetime(all_df['date'])
    all_df['year'] = all_df['date'].dt.year
    all_df['month'] = all_df['date'].dt.month
    all_df['week'] = all_df['date'].dt.isocalendar().week

    all_df['class_start_time'] = np.where(all_df['progress'].isin(['请假', '取消']), 0, all_df['class_start_time'])
    all_df['class_end_time'] = np.where(all_df['progress'].isin(['请假', '取消']), 0, all_df['class_end_time'])
    all_df['class_start_time'] = pd.to_timedelta(all_df['class_start_time'].astype(str), errors='coerce')
    all_df['class_end_time'] = pd.to_timedelta(all_df['class_end_time'].astype(str), errors='coerce')

    all_df['class_duration'] = all_df['class_end_time'] - all_df['class_start_time']
    all_df['class_duration'] = all_df['class_duration'].dt.total_seconds() / 3600
    all_df['class_duration'] = np.where(all_df['content'] == '辅导',
                                        all_df['class_duration'] * 1/4,
                                        all_df['class_duration'])
    all_df['class_type'] = np.where(all_df['content'] == '辅导', 'tut', 'class')
    return all_df

# ========== Sidebar: file upload ==========
st.sidebar.header("📂 Data Source")
uploaded_file = st.sidebar.file_uploader("Upload nh_tracking.xlsx", type=["xlsx"])

if uploaded_file is None:
    st.info("👈 Please upload your nh_tracking.xlsx file from the left sidebar.")
    st.stop()

all_df = load_data(uploaded_file)

# ========== Sidebar: filters (default to current year/month) ==========
st.sidebar.header("🔍 Filters")

now = datetime.now()
current_year = now.year
current_month = now.month

years = sorted(all_df['year'].dropna().unique().tolist())
default_years = [current_year] if current_year in years else years[-1:]

months = sorted(all_df['month'].dropna().unique().tolist())
default_months = [current_month] if current_month in months else months[-1:]

selected_years = st.sidebar.multiselect("Year", years, default=default_years)
selected_months = st.sidebar.multiselect("Month", months, default=default_months)

filtered = all_df[
    all_df['year'].isin(selected_years) & all_df['month'].isin(selected_months)
]

if filtered.empty:
    st.warning("No data matches the current filters.")
    st.stop()

# ========== Sidebar: settings (persisted) ==========
st.sidebar.header("⚙️ Settings")

# 1) Base salary
has_base_salary = st.sidebar.radio(
    "Do you have a base salary?",
    options=["No", "Yes"],
    index=0 if st.session_state.has_base_salary == "No" else 1,
)

if has_base_salary == "Yes":
    base_salary = st.sidebar.number_input(
        "Base salary (¥)",
        min_value=0.0,
        value=float(st.session_state.base_salary),
        step=100.0,
    )
else:
    base_salary = 0.0

# 2) Obligatory hours / hourly rate
has_obligation = st.sidebar.radio(
    "Are there obligatory hours?",
    options=["No", "Yes"],
    index=0 if st.session_state.has_obligation == "No" else 1,
)

rules = []

if has_obligation == "No":
    rate = st.sidebar.number_input(
        "Hourly rate (¥)",
        min_value=0.0,
        value=float(st.session_state.flat_rate),
        step=10.0,
    )
    obligation_hours = 0.0
    pay_mode = "flat"
else:
    obligation_hours = st.sidebar.number_input(
        "Obligatory hours",
        min_value=0.0,
        value=float(st.session_state.obligation_hours),
        step=1.0,
    )

    st.sidebar.markdown("**Tiered rates for hours beyond obligation**")
    st.sidebar.caption(
        "Set an upper bound and an hourly rate per tier. "
        'Leave the last tier\'s upper bound blank to mean "and above".'
    )

    for i, rule in enumerate(st.session_state.rules):
        c1, c2, c3 = st.sidebar.columns([2, 2, 1])
        upper_val = rule["upper"] if rule["upper"] is not None else 0.0

        new_upper = c1.number_input(
            f"Up to (h) #{i+1}",
            min_value=0.0,
            value=float(upper_val),
            step=1.0,
            key=f"upper_{i}",
        )
        new_rate = c2.number_input(
            f"Rate (¥) #{i+1}",
            min_value=0.0,
            value=float(rule["rate"]),
            step=10.0,
            key=f"rate_{i}",
        )

        if i == len(st.session_state.rules) - 1:
            rule["upper"] = None
        else:
            rule["upper"] = new_upper
        rule["rate"] = new_rate

        if c3.button("❌", key=f"del_{i}"):
            st.session_state.rules.pop(i)
            flat_rate = locals().get("rate", st.session_state.flat_rate)
            save_settings(has_base_salary, base_salary, has_obligation,
                          obligation_hours, flat_rate, st.session_state.rules)
            st.rerun()

    if st.sidebar.button("➕ Add tier"):
        st.session_state.rules.append({"upper": None, "rate": 200.0})
        flat_rate = locals().get("rate", st.session_state.flat_rate)
        save_settings(has_base_salary, base_salary, has_obligation,
                      obligation_hours, flat_rate, st.session_state.rules)
        st.rerun()

    rules = st.session_state.rules
    pay_mode = "tiered"

# Persist settings on every run
flat_rate = locals().get("rate", st.session_state.flat_rate)
save_settings(has_base_salary, base_salary, has_obligation,
              obligation_hours, flat_rate, rules)

# ========== Payment calculation ==========
def calc_fee(total_hours, base_salary, obligation_hours, pay_mode, flat_rate=None, rules=None):
    """
    Returns (total_payment, breakdown_list).
    total_payment = base_salary + hourly_payment

    Obligatory hours are unpaid.
    Only hours beyond obligation_hours are paid, at the tier rate corresponding to the absolute hour band.
    """
    detail = []

    if base_salary > 0:
        detail.append({"Tier": "Base salary", "Hours": "-", "Rate": "-",
                       "Subtotal": round(base_salary, 2)})

    if pay_mode == "flat":
        fee = total_hours * flat_rate
        detail.append({"Tier": "All hours", "Hours": round(total_hours, 2),
                       "Rate": flat_rate, "Subtotal": round(fee, 2)})
        return base_salary + fee, detail

    # tiered mode: obligation is unpaid, tiers are on absolute hours
    if obligation_hours > 0:
        detail.append({"Tier": f"Obligatory (first {obligation_hours} h)",
                       "Hours": round(min(total_hours, obligation_hours), 2),
                       "Rate": 0, "Subtotal": 0})

    fee = 0.0
    prev_upper = obligation_hours  # lower bound of first paid tier = obligation

    for rule in rules:
        upper = rule["upper"]  # absolute hour upper bound (None = no limit)
        rate = rule["rate"]

        # Skip tiers that end at or before the obligation threshold
        if upper is not None and upper <= obligation_hours:
            continue

        # Hours in this tier = overlap of (obligation, total] with (prev_upper, upper]
        tier_lower = max(prev_upper, obligation_hours)
        tier_upper = total_hours if upper is None else min(upper, total_hours)

        if tier_upper <= tier_lower:
            # No hours fall in this tier; still advance prev_upper
            if upper is not None:
                prev_upper = upper
            continue

        hours_in_tier = tier_upper - tier_lower

        if upper is None:
            label = f"{tier_lower}+ h"
        else:
            label = f"{tier_lower} – {upper} h"

        subtotal = hours_in_tier * rate
        fee += subtotal
        detail.append({"Tier": label, "Hours": round(hours_in_tier, 2),
                       "Rate": rate, "Subtotal": round(subtotal, 2)})

        if upper is not None:
            prev_upper = upper
        else:
            break  # last tier is unbounded

    return base_salary + fee, detail

# ========== Top metrics ==========
total_class = filtered.loc[filtered['class_type'] == 'class', 'class_duration'].sum()
total_tut = filtered.loc[filtered['class_type'] == 'tut', 'class_duration'].sum()
total_hrs = total_class + total_tut

col1, col2, col3 = st.columns(3)
col1.metric("Regular class hours", f"{total_class:.2f} h")
col2.metric("Tutoring hours (converted)", f"{total_tut:.2f} h")
col3.metric("Total hours", f"{total_hrs:.2f} h")

# ========== Payment summary ==========
if pay_mode == "flat":
    fee, fee_detail = calc_fee(total_hrs, base_salary, 0, "flat", flat_rate=flat_rate)
else:
    fee, fee_detail = calc_fee(total_hrs, base_salary, obligation_hours, "tiered", rules=rules)

st.subheader("💰 Payment Summary")
c1, c2 = st.columns([1, 2])
c1.metric("Total payment", f"¥{fee:,.2f}")

with c2:
    with st.expander("View payment breakdown", expanded=False):
        st.dataframe(pd.DataFrame(fee_detail), use_container_width=True, hide_index=True)

# ========== Weekly table ==========
st.subheader("📅 Weekly Hours")
tbl_wk = filtered.groupby(['year', 'week', 'class_type'])['class_duration'].sum().reset_index().pivot(
    index=['year', 'week'], columns='class_type', values='class_duration'
).fillna(0).reset_index()
if 'class' not in tbl_wk.columns:
    tbl_wk['class'] = 0
if 'tut' not in tbl_wk.columns:
    tbl_wk['tut'] = 0
tbl_wk['total'] = tbl_wk['class'] + tbl_wk['tut']
tbl_wk = tbl_wk.round(2)

date_week = filtered[['date', 'year', 'week', 'days_of_week']].dropna(how="any")
date_week_wide = date_week[date_week['days_of_week'].isin([1.0, 7.0])].pivot(
    index=['year', 'week'], columns='days_of_week', values='date'
).reset_index().rename(columns={1.0: 'start', 7.0: 'end'})
date_week_wide['date_range'] = date_week_wide['start'].astype(str) + ' to ' + date_week_wide['end'].astype(str)
tbl_wk = pd.merge(date_week_wide[['year', 'week', 'date_range']], tbl_wk, on=['year', 'week'], how='left')
tbl_wk = tbl_wk.rename(columns={
    'year': 'Year', 'week': 'Week', 'date_range': 'Date range',
    'class': 'Regular (h)', 'tut': 'Tutoring (h)', 'total': 'Total (h)'
})
st.dataframe(tbl_wk, use_container_width=True, hide_index=True)

# ========== Monthly table ==========
st.subheader("🗓️ Monthly Hours")
tbl_mth = filtered.groupby(['year', 'month', 'class_type'])['class_duration'].sum().reset_index().pivot(
    index=['year', 'month'], columns='class_type', values='class_duration'
).fillna(0).reset_index()
if 'class' not in tbl_mth.columns:
    tbl_mth['class'] = 0
if 'tut' not in tbl_mth.columns:
    tbl_mth['tut'] = 0
tbl_mth['total'] = tbl_mth['class'] + tbl_mth['tut']
tbl_mth = tbl_mth.round(2)

monthly_fees = []
for _, row in tbl_mth.iterrows():
    mth_hrs = row['total']
    if pay_mode == "flat":
        m_fee, _ = calc_fee(mth_hrs, base_salary, 0, "flat", flat_rate=flat_rate)
    else:
        m_fee, _ = calc_fee(mth_hrs, base_salary, obligation_hours, "tiered", rules=rules)
    monthly_fees.append(round(m_fee, 2))
tbl_mth['fee'] = monthly_fees
tbl_mth = tbl_mth.rename(columns={
    'year': 'Year', 'month': 'Month',
    'class': 'Regular (h)', 'tut': 'Tutoring (h)', 'total': 'Total (h)', 'fee': 'Payment (¥)'
})
st.dataframe(tbl_mth, use_container_width=True, hide_index=True)

# ========== Extra hours ==========
st.subheader("⏱️ Month-End Cumulative Extra Hours")

tmp = all_df[['year', 'month', 'note']].dropna()
tmp['cumsum_mth'] = tmp.groupby(['year', 'month'])['note'].cumsum()
last_idx = tmp.groupby(['year', 'month']).tail(1).index
tmp1 = tmp.loc[last_idx,].reset_index(drop=True).drop(columns=['note'])
pre_value = 0
for i in range(len(tmp1)):
    current_sum = tmp1.loc[tmp1.index[i], 'cumsum_mth']
    current_sum += max(pre_value, 0)
    tmp1.loc[tmp1.index[i], 'cumsum_mth'] = current_sum
    pre_value = current_sum if current_sum > 0 else 0

tmp1 = tmp1.rename(columns={
    'year': 'Year', 'month': 'Month', 'cumsum_mth': 'Cumulative extra hours (h)'
})
st.dataframe(tmp1, use_container_width=True, hide_index=True)

# ========== Downloads ==========
st.subheader("📥 Export")
col_a, col_b = st.columns(2)
with col_a:
    st.download_button(
        "Download weekly CSV",
        tbl_wk.to_csv(index=False).encode('utf-8-sig'),
        file_name="weekly_hours.csv",
        mime="text/csv"
    )
with col_b:
    st.download_button(
        "Download monthly CSV",
        tbl_mth.to_csv(index=False).encode('utf-8-sig'),
        file_name="monthly_hours.csv",
        mime="text/csv"
    )