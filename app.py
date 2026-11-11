import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import os
import qrcode
from io import BytesIO
from PIL import Image
import requests
import cv2
import numpy as np
import json
import hashlib
import base64
import barcode
from barcode.writer import ImageWriter
import google.generativeai as genai
from supabase import create_client, Client

# --- TÜRKİYE SAAT DİLİMİ (UTC+3) ---
TR_TZ = timezone(timedelta(hours=3))

st.set_page_config(page_title="MİDES - Akıllı Depo", page_icon="📦", layout="wide")

# ==========================================================
# 🚀 MİDES AKILLI TEMA (LIGHT & DARK MOD UYUMLU CSS)
# ==========================================================
responsive_css = """
<style>
/* Sekmelerin mobilde ve masaüstünde taşmasını önleyen ve net okunmasını sağlayan ayar */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    padding: 8px;
    border-radius: 12px;
    overflow-x: auto;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    font-weight: 600;
    padding: 8px 16px;
}
/* Butonlar ve Formlar */
.stButton > button {
    border-radius: 10px !important;
    font-weight: 700 !important;
}
[data-testid="stDataFrame"] {
    border-radius: 12px;
    overflow: hidden;
}
.stAlert {
    border-radius: 12px !important;
}
</style>
"""
st.markdown(responsive_css, unsafe_allow_html=True)

def sifre_hashle(sifre):
    return hashlib.sha256(str(sifre).encode('utf-8')).hexdigest()

def rakam_temizle(deger):
    try:
        if pd.isna(deger) or str(deger).strip() == "": return 0.0
        d_str = str(deger).upper().replace('KG', '').replace('LİTRE', '').replace('ADET', '').replace(' ', '').strip()
        if '.' in d_str and ',' in d_str: d_str = d_str.replace('.', '').replace(',', '.')
        elif ',' in d_str: d_str = d_str.replace(',', '.')
        return float(d_str)
    except:
        return 0.0

# --- GÜVENLİ SUPABASE BAĞLANTISI ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"].strip().rstrip("/")
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"].strip()
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"⚠️ Supabase bağlantı hatası: {e}")
    st.stop()

def tablo_isimleri_degistir(df):
    rename_dict = {
        "id": "ID", "stok_no": "Stok No", "urun_adi": "Ürün Adı", "miktar": "Miktar",
        "birim": "Birim", "eklenme_tarihi": "Eklenme Tarihi", "skt": "SKT",
        "uretim_tarihi": "Üretim Tarihi", "giris_tarihi": "Giriş Tarihi",
        "resim_yolu": "Resim Yolu", "kritik_stok": "Kritik Stok", "alim_turu": "Alım Türü",
        "sozlesme_no": "Sözleşme No", "sozlesme_tarihi": "Sözleşme Tarihi",
        "sozlesme_bitis_tarihi": "Sözleşme Bitiş Tarihi", "sozlesme_kritik": "Sözleşme Kritik",
        "firma": "Firma", "tarih": "Tarih", "kullanici": "Kullanıcı", "islem": "İşlem",
        "aciklama": "Açıklama", "kullanici_adi": "Kullanıcı Adı", "sifre": "Şifre",
        "yetki": "Yetki", "telegram_token": "Telegram Token", "chat_id": "Chat ID",
        "ilk_giris": "İlk Giriş", "son_guncelleme": "Son Güncelleme", "mesaj": "Mesaj",
        "aktif": "Aktif", "tur": "Tür", "sayim_eksigi": "Sayım Eksiği"
    }
    df.rename(columns=rename_dict, inplace=True)
    return df

def verileri_getir(tablo_adi):
    try:
        res = supabase.table(tablo_adi).select("*").execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            df = tablo_isimleri_degistir(df)
            if 'Firma' in df.columns and st.session_state.get('rol') != 'admin':
                df = df[df['Firma'].astype(str) == st.session_state['firma']]
        return df
    except Exception as e:
        st.error(f"Veri çekme hatası ({tablo_adi}): {e}")
        return pd.DataFrame()

def hareketleri_getir():
    try:
        res = supabase.table('hareket_gecmisi').select("*").execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            df = tablo_isimleri_degistir(df)
            if st.session_state.get('rol') != 'admin':
                df = df[df['Firma'].astype(str) == st.session_state['firma']]
            return df.sort_values(by="ID", ascending=False)
    except Exception:
        pass
    return pd.DataFrame(columns=["ID", "Tarih", "Kullanıcı", "İşlem", "Ürün Adı", "Miktar", "Açıklama", "Firma"])

def log_kaydet(kullanici, islem_tipi, urun_adi, miktar, aciklama):
    try:
        zaman = datetime.now(TR_TZ).strftime('%Y-%m-%d %H:%M:%S')
        firma_adi = st.session_state.get('firma', 'Bilinmiyor')
        veri = {
            "tarih": zaman, "kullanici": kullanici, "islem": islem_tipi,
            "urun_adi": urun_adi, "miktar": miktar, "aciklama": aciklama, "firma": firma_adi
        }
        supabase.table('hareket_gecmisi').insert(veri).execute()
    except Exception as e:
        st.warning(f"Log kaydedilemedi: {e}")

def qr_olustur(metin):
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(metin)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def barkod_olustur(metin):
    try:
        rv = barcode.get('code128', str(metin), writer=ImageWriter())
        buf = BytesIO()
        rv.write(buf, options={'write_text': True, 'dpi': 200, 'module_width': 0.5, 'module_height': 8.0})
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        return None

def telegram_mesaj_gonder(mesaj):
    if 'telegram_token' in st.session_state and 'telegram_chat_id' in st.session_state:
        token = st.session_state['telegram_token']
        chat_id = st.session_state['telegram_chat_id']
        if token and chat_id and str(token).lower() != "nan" and str(chat_id).lower() != "nan":
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": mesaj}
            try: requests.post(url, data=payload)
            except: pass

# --- OTURUM YÖNETİMİ ---
if 'giris_yapildi' not in st.session_state:
    st.session_state.update({'giris_yapildi': False, 'kullanici': "", 'rol': "", 'firma': "", 'sifre_degistirme_modu': False, 'ilk_giris_uyarisi': False})

try:
    kullanicilar_res = supabase.table('kullanicilar').select("*").execute()
    df_kullanicilar = tablo_isimleri_degistir(pd.DataFrame(kullanicilar_res.data)) if kullanicilar_res.data else pd.DataFrame()
except Exception as e:
    st.error(f"🚨 Supabase bağlantı hatası: {e}")
    st.stop()

if st.session_state['sifre_degistirme_modu']:
    if st.session_state.get('ilk_giris_uyarisi'): 
        st.warning("⚠️ İlk giriş! Lütfen yeni güvenli şifrenizi belirleyin.")
    else: 
        st.warning("⚠️ Şifre süresi doldu. Lütfen yeni şifre belirleyin.")
        
    with st.form("sifre_degistir_formu"):
        yeni_sifre = st.text_input("Yeni Şifre:", type="password")
        yeni_sifre_tekrar = st.text_input("Yeni Şifre (Tekrar):", type="password")
        
        if st.form_submit_button("Şifreyi Güncelle"):
            if yeni_sifre == yeni_sifre_tekrar and len(yeni_sifre) >= 4:
                kullanici_id = int(df_kullanicilar[df_kullanicilar['Kullanıcı Adı'] == st.session_state['kullanici']].iloc[0]['ID'])
                bugun = datetime.now(TR_TZ).strftime('%Y-%m-%d')
                supabase.table('kullanicilar').update({
                    "sifre": sifre_hashle(yeni_sifre), "son_guncelleme": bugun, "ilk_giris": "Hayır"
                }).eq("id", kullanici_id).execute()
                st.success("✅ Şifre güncellendi! Yeniden giriş yapın.")
                st.session_state.update({'sifre_degistirme_modu': False, 'giris_yapildi': False, 'ilk_giris_uyarisi': False})
                st.stop()
            else: st.error("Şifreler uyuşmuyor veya çok kısa.")
    st.stop()

if not st.session_state['giris_yapildi']:
    st.markdown("<h1 style='text-align: center; margin-top: 50px;'>🔐 MİDES Depo Yönetim Sistemi</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            kadi_input = st.text_input("Kullanıcı Adı")
            sifre_input = st.text_input("Şifre", type="password")
            if st.form_submit_button("Giriş Yap", use_container_width=True):
                if df_kullanicilar.empty:
                    st.error("Kullanıcı bulunamadı!")
                    st.stop()
                girilen_hash = sifre_hashle(sifre_input)
                kullanici = df_kullanicilar[
                    (df_kullanicilar['Kullanıcı Adı'] == kadi_input) & 
                    ((df_kullanicilar['Şifre'].astype(str) == str(sifre_input)) | (df_kullanicilar['Şifre'].astype(str) == girilen_hash))
                ]
                if not kullanici.empty:
                    yetki = str(kullanici['Yetki'].values[0]).strip().lower()
                    if yetki in ["gida", "gıda", "temizlik", "yonetici", "yönetici", "merkez yönetici"]:
                        st.session_state['kullanici'] = kadi_input
                        firma = str(kullanici['Firma'].values[0]).strip() if 'Firma' in kullanici else kadi_input
                        st.session_state['firma'] = firma if firma and firma.lower() != "nan" else kadi_input
                        st.session_state['rol'] = "admin" if yetki in ["yonetici", "yönetici", "merkez yönetici"] else ("gida" if yetki in ["gida", "gıda"] else "temizlik")
                        st.session_state['telegram_token'] = str(kullanici['Telegram Token'].values[0]) if 'Telegram Token' in kullanici else ""
                        st.session_state['telegram_chat_id'] = str(kullanici['Chat ID'].values[0]) if 'Chat ID' in kullanici else ""
                        
                        if str(kullanici['İlk Giriş'].values[0]).strip().lower() == "evet":
                            st.session_state.update({'sifre_degistirme_modu': True, 'ilk_giris_uyarisi': True})
                            st.rerun()
                        else:
                            st.session_state['giris_yapildi'] = True
                            st.rerun()
                    else: st.error("❌ Yetkiniz yok!")
            else: st.error("❌ Kullanıcı adı veya şifre hatalı!")
else:
    # --- ANA ARAYÜZ ---
    if st.session_state['rol'] == 'admin':
        st.info("👑 **Merkezi Yönetici Modu**")
        secilen_depo = st.selectbox("Aktif Depo", ["🍎 Gıda Deposu", "🧹 Temizlik Deposu"])
        aktif_tablo = "gida_deposu" if "Gıda" in secilen_depo else "temizlik_deposu"
        depo_adi = "Gıda Deposu" if "Gıda" in secilen_depo else "Temizlik Deposu"
    else:
        aktif_tablo = "gida_deposu" if st.session_state['rol'] == 'gida' else "temizlik_deposu"
        depo_adi = "Gıda Deposu" if st.session_state['rol'] == 'gida' else "Temizlik Deposu"

    df = verileri_getir(aktif_tablo)
    if not df.empty and 'Sayım Eksiği' not in df.columns: df['Sayım Eksiği'] = 0.0
    if not df.empty: df['Sayım Eksiği'] = pd.to_numeric(df['Sayım Eksiği'], errors='coerce').fillna(0)
    bugun = datetime.now(TR_TZ).date()
                        
    c_ust1, c_ust2 = st.columns([4, 1])
    with c_ust1: st.title(f"📦 {st.session_state['firma']} - {depo_adi}")
    with c_ust2:
        st.write(f"👤 {st.session_state['kullanici']}")
        if st.button("🔄 Şifre Değiştir"):
            st.session_state['sifre_degistirme_modu'] = True
            st.rerun()
        if st.button("🚪 Çıkış Yap"):
            st.session_state['giris_yapildi'] = False
            st.rerun()

    try:
        res_duyuru = supabase.table('duyurular').select("*").execute()
        if res_duyuru.data and str(res_duyuru.data[0].get('aktif', '')) == 'Evet':
            st.warning(f"📢 **DUYURU:** {res_duyuru.data[0].get('mesaj', '')}")
    except Exception: pass

    # ==========================================
    # 📑 KLASİK SEKMELİ YAPI (LIGHT & DARK UYUMLU)
    # ==========================================
    if st.session_state['rol'] == 'admin':
        sekme1, sekme2, sekme3, sekme12, sekme6, sekme4, sekme5, sekme7, sekme8, sekme9, sekme10, sekme11 = st.tabs([
            "📊 Özet", "➕ Ekle", "🔄 Güncelle", "📋 Sayım", "⚡ Hızlı", "🪪 Etiket", "📝 Geçmiş", "📑 Sözleşme", "💬 Bildirim", "👥 Kullanıcı", "📢 Duyuru", "📂 Çıkış"
        ])
    else:
        sekme1, sekme2, sekme3, sekme12, sekme6, sekme4, sekme5, sekme7, sekme8, sekme11 = st.tabs([
            "📊 Özet", "➕ Ekle", "🔄 Güncelle", "📋 Sayım", "⚡ Hızlı", "🪪 Etiket", "📝 Geçmiş", "📑 Sözleşme", "💬 Bildirim", "📂 Çıkış"
        ])

    with sekme1:
        st.markdown(f"### 📋 Uyarılar")
        krt_sayisi = 0
        telegram_raporu = f"⚠️ {st.session_state['firma']} - {depo_adi.upper()} UYARI RAPORU ⚠️\n\n"
        
        if not df.empty:
            for index, row in df.iterrows():
                urun_adi = str(row.get('Ürün Adı', 'Bilinmeyen')).strip()
                stok_no = str(row.get('Stok No', '-'))
                miktar_metni = str(row.get('Miktar', '0')).strip()
                birim = str(row.get('Birim', '')).strip()
                try:
                    skt_metni = str(row.get('SKT', '')).strip()
                    if skt_metni and skt_metni != "-" and skt_metni.lower() != "nan":
                        skt = datetime.strptime(skt_metni, '%Y-%m-%d').date()
                        kalan = (skt - bugun).days
                        if kalan < 0:
                            st.error(f"❌ {urun_adi} - TARİHİ GEÇTİ! ({skt_metni})")
                            telegram_raporu += f"❌ {urun_adi} - TARİHİ GEÇTİ!\n"
                            krt_sayisi += 1
                        elif 0 <= kalan <= 30:
                            st.warning(f"⚠️ {urun_adi} - SKT'ye {kalan} gün kaldı! ({skt_metni})")
                            telegram_raporu += f"⚠️ {urun_adi} - {kalan} gün kaldı!\n"
                            krt_sayisi += 1
                except: pass
                try:
                    kritik = float(str(row.get('Kritik Stok', '10')).strip() or '10')
                    M = float(miktar_metni if miktar_metni and miktar_metni.lower() != "nan" else 0)
                    if M <= kritik:
                        st.error(f"📉 STOK ALARMI: {urun_adi} bitmek üzere! (Kalan: {M} {birim})")
                        telegram_raporu += f"📉 ALARM: {urun_adi} (Kalan: {M} {birim})\n"
                        krt_sayisi += 1
                except: pass

        if krt_sayisi == 0: st.success("✅ Depo durumu çok iyi. Uyarı bulunmuyor.")
        if st.button("📲 Telegram'a Rapor Gönder"):
            telegram_mesaj_gonder(telegram_raporu)
            st.toast("✅ Gönderildi!")
            
        st.divider()
        st.markdown("### 📦 Stok Numarasına Göre Genel Toplamlar")
        if not df.empty:
            df['Miktar_Sayi'] = pd.to_numeric(df['Miktar'], errors='coerce').fillna(0)
            toplam_stok_df = df.groupby('Stok No').agg({'Ürün Adı': 'first', 'Miktar_Sayi': 'sum', 'Birim': 'first'}).reset_index()
            toplam_stok_df.rename(columns={'Miktar_Sayi': 'Toplam Miktar'}, inplace=True)
            st.dataframe(toplam_stok_df[['Stok No', 'Ürün Adı', 'Toplam Miktar', 'Birim']], use_container_width=True, hide_index=True)

            st.markdown("### 🔍 Detaylı Parti Listesi")
            st.dataframe(df.drop(columns=['Resim Yolu', 'Miktar_Sayi', 'Depo Sahibi', 'Firma'], errors='ignore'), use_container_width=True, hide_index=True)
        else:
            st.info("Depoda ürün bulunmuyor.")

        if st.session_state['rol'] == 'admin':
            st.divider()
            st.markdown("### 📈 Firma Aktivite Analizi")
            df_perf = hareketleri_getir()
            if not df_perf.empty and 'Firma' in df_perf.columns:
                c_g1, c_g2 = st.columns(2)
                with c_g1: st.bar_chart(df_perf['Firma'].value_counts())
                with c_g2:
                    son_gorme = df_perf.groupby('Firma')['Tarih'].max().reset_index()
                    son_gorme.columns = ['Firma', 'Son İşlem Tarihi']
                    st.dataframe(son_gorme.sort_values('Son İşlem Tarihi', ascending=False), use_container_width=True, hide_index=True)

    with sekme2:
        st.subheader("➕ Depoya Yeni Ürün Ekle")
        ekleme_yontemi = st.radio("Yöntem Seçin:", ["📝 Manuel Form", "📸 Yapay Zeka ile İrsaliye/Fatura Okut"], horizontal=True)

        if "Manuel" in ekleme_yontemi:
            with st.form("urun_ekle_formu"):
                col1, col2 = st.columns(2)
                with col1:
                    stok_no = st.text_input("Stok Numarası (Barkod)")
                    urun_adi = st.text_input("Ürün Adı")
                    miktar = st.number_input("Miktar", min_value=0.0, step=1.0)
                    birim = st.selectbox("Birim", ["Kg", "Litre", "Adet", "Kutu", "Paket", "Koli"])
                    alim_turu = st.selectbox("Alım Türü", ["Merkezi Alım", "Piyasa Alımı"])
                with col2:
                    kritik_seviye = st.number_input("Kritik Uyarı Seviyesi", min_value=1, value=20)
                    uretim_tarihi = st.date_input("Üretim Tarihi")
                    skt = st.date_input("Son Kullanma Tarihi (SKT)")
                    st.markdown("---")
                    sozlesme_no = st.text_input("Sözleşme No")
                    sozlesme_tarihi = st.date_input("Sözleşme Tarihi")
                    sozlesme_bitis = st.date_input("Sözleşme Bitiş")
                    sozlesme_kritik = st.number_input("Sözleşme Kritik Sınırı", min_value=0.0, value=20.0)
                    ekle_btn = st.form_submit_button("Ürünü Kaydet")
            if ekle_btn:
                if urun_adi and stok_no:
                    bugun_tarih = datetime.now(TR_TZ).strftime("%Y-%m-%d")
                    yeni_veri = {
                        "stok_no": stok_no, "urun_adi": urun_adi, "miktar": miktar, "birim": birim,
                        "eklenme_tarihi": bugun_tarih, "skt": str(skt), "uretim_tarihi": str(uretim_tarihi),
                        "giris_tarihi": bugun_tarih, "resim_yolu": "", "kritik_stok": kritik_seviye,
                        "alim_turu": alim_turu, "sozlesme_no": sozlesme_no if alim_turu == "Piyasa Alımı" else "-",
                        "sozlesme_tarihi": str(sozlesme_tarihi) if alim_turu == "Piyasa Alımı" else "-",
                        "sozlesme_bitis_tarihi": str(sozlesme_bitis) if alim_turu == "Piyasa Alımı" else "-",
                        "sozlesme_kritik": sozlesme_kritik if alim_turu == "Piyasa Alımı" else 0.0,
                        "sayim_eksigi": 0, "firma": st.session_state['firma']
                    }
                    supabase.table(aktif_tablo).insert(yeni_veri).execute()
                    log_kaydet(st.session_state['kullanici'], "YENİ KAYIT", urun_adi, miktar, "Manuel eklendi")
                    st.success("✅ Ürün kaydedildi!")
                    st.rerun()
                else: st.error("Stok No ve Ürün Adı zorunludur.")
        else:
            st.info("💡 Fatura veya irsaliye fotoğrafı yükleyin, yapay zeka okusun.")
            resim_dosyasi_giris = st.file_uploader("Fotoğraf Yükle", type=['jpg', 'jpeg', 'png'], key="giris_foto")
            if resim_dosyasi_giris and st.button("🤖 Yapay Zekaya Okut"):
                with st.spinner("Okunuyor..."):
                    try:
                        gemini_api_key = st.secrets.get("GEMINI_API_KEY", "").strip()
                        genai.configure(api_key=gemini_api_key)
                        model = genai.GenerativeModel('gemini-3.5-flash')
                        prompt = "Tablodaki malzemeleri oku ve her satır için 'Stok No', 'Ürün Adı', 'Miktar', 'Birim' çıkar. Sadece JSON dizisi döndür: [{\"Stok No\": \"...\", \"Ürün Adı\": \"...\", \"Miktar\": \"...\", \"Birim\": \"...\"}]"
                        response = model.generate_content([prompt, Image.open(resim_dosyasi_giris)])
                        json_text = response.text.strip().replace("```json", "").replace("```", "").strip()
                        st.session_state['ai_giris_df'] = pd.DataFrame(json.loads(json_text))
                        st.success("✅ Okundu!")
                    except Exception as e: st.error(f"Hata: {e}")

            if 'ai_giris_df' in st.session_state and st.session_state['ai_giris_df'] is not None:
                with st.form("toplu_giris_onay"):
                    duzenlenmis_giris = st.data_editor(st.session_state['ai_giris_df'], use_container_width=True, hide_index=True)
                    c1, c2 = st.columns(2)
                    if c1.form_submit_button("💾 Depoya Ekle"):
                        for _, r in duzenlenmis_giris.iterrows():
                            s_no = str(r.get('Stok No', '')).strip()
                            u_adi = str(r.get('Ürün Adı', '')).strip()
                            m_val = float(r.get('Miktar', 0) or 0)
                            b_val = str(r.get('Birim', 'Adet')).strip()
                            if u_adi and m_val > 0 and s_no:
                                supabase.table(aktif_tablo).insert({
                                    "stok_no": s_no, "urun_adi": u_adi, "miktar": m_val, "birim": b_val,
                                    "eklenme_tarihi": bugun.strftime('%Y-%m-%d'), "skt": bugun.strftime('%Y-%m-%d'),
                                    "uretim_tarihi": bugun.strftime('%Y-%m-%d'), "giris_tarihi": bugun.strftime('%Y-%m-%d'),
                                    "resim_yolu": "", "kritik_stok": 10, "alim_turu": "Merkezi Alım",
                                    "sozlesme_no": "-", "sozlesme_tarihi": "-", "sozlesme_bitis_tarihi": "-",
                                    "sozlesme_kritik": 0.0, "sayim_eksigi": 0, "firma": st.session_state['firma']
                                }).execute()
                                log_kaydet(st.session_state['kullanici'], "YENİ KAYIT", u_adi, m_val, "AI Toplu Ekleme")
                        st.session_state['ai_giris_df'] = None
                        st.success("✅ Ürünler eklendi!")
                        st.rerun()

    with sekme3:
        st.subheader("🔄 Ürün Güncelle ve Sil")
        if not df.empty:
            secili = st.selectbox("Ürün Seçin:", df['ID'].astype(str) + " - " + df['Ürün Adı'])
            s_id = int(secili.split(" - ")[0])
            urun = df[df['ID'] == s_id].iloc[0]
            u_mik = int(float(str(urun.get('Miktar', '0')).strip() or '0'))
            with st.form("guncelle"):
                c1, c2 = st.columns(2)
                y_stok = c1.text_input("Stok No:", value=str(urun.get('Stok No', '')))
                cikis = c1.number_input("➖ Çıkış:", min_value=0, max_value=u_mik, step=1)
                giris = c1.number_input("➕ Giriş:", min_value=0, step=1)
                y_kritik = c2.number_input("Kritik Sınır:", value=int(float(str(urun.get('Kritik Stok', '10')).strip() or '10')))
                
                b1, b2 = st.columns(2)
                if b1.form_submit_button("💾 Kaydet"):
                    yeni_m = u_mik - cikis + giris
                    supabase.table(aktif_tablo).update({"stok_no": y_stok, "miktar": yeni_m, "kritik_stok": y_kritik}).eq("id", s_id).execute()
                    if cikis > 0: log_kaydet(st.session_state['kullanici'], "ÇIKIŞ", urun['Ürün Adı'], cikis, "Güncelleme")
                    if giris > 0: log_kaydet(st.session_state['kullanici'], "GİRİŞ", urun['Ürün Adı'], giris, "Güncelleme")
                    st.success("Güncellendi!")
                    st.rerun()
                if b2.form_submit_button("🗑️ Ürünü Sil"):
                    supabase.table(aktif_tablo).delete().eq("id", s_id).execute()
                    log_kaydet(st.session_state['kullanici'], "SİLME", urun['Ürün Adı'], u_mik, "Silindi")
                    st.success("Silindi!")
                    st.rerun()

    with sekme12:
        st.subheader("📋 Depo Sayımı ve Eksik Takibi")
        if not df.empty:
            eksikler = df[df['Sayım Eksiği'] > 0]
            if not eksikler.empty:
                st.error("🚨 **GEÇMİŞTEN KALAN EKSİKLER:**")
                st.dataframe(eksikler[['Stok No', 'Ürün Adı', 'Sayım Eksiği', 'Birim']], hide_index=True, use_container_width=True)
            
            sayim_df = df[['ID', 'Stok No', 'Ürün Adı', 'Miktar', 'Sayım Eksiği', 'Birim']].copy()
            sayim_df.rename(columns={'Miktar': 'Sistemdeki Miktar', 'Sayım Eksiği': 'Bilinen Eksik Miktar'}, inplace=True)
            sayim_df['Raftaki Gerçek Sayı'] = sayim_df['Sistemdeki Miktar']
            
            with st.form("sayim_formu"):
                duzenlenmis = st.data_editor(sayim_df, column_config={"Raftaki Gerçek Sayı": st.column_config.NumberColumn("✏️ Raftaki Gerçek Sayı", min_value=0.0)}, disabled=["ID", "Stok No", "Ürün Adı", "Sistemdeki Miktar", "Bilinen Eksik Miktar", "Birim"], hide_index=True, use_container_width=True)
                if st.form_submit_button("💾 Farkları Hesapla ve Güncelle"):
                    duzenlenmis['Fark'] = duzenlenmis['Raftaki Gerçek Sayı'] - duzenlenmis['Sistemdeki Miktar']
                    farklar = duzenlenmis[duzenlenmis['Fark'] != 0]
                    if farklar.empty: st.success("✅ Sayım eksiksiz eşleşiyor.")
                    else:
                        for _, row in farklar.iterrows():
                            u_id = int(row['ID'])
                            y_m = float(row['Raftaki Gerçek Sayı'])
                            fark = float(row['Fark'])
                            e_eksik = float(row['Bilinen Eksik Miktar'])
                            if fark < 0:
                                y_eksik = e_eksik + abs(fark)
                                tip, acik = "SAYIM EKSİĞİ (ÇIKIŞ)", f"Yeni eksik: {abs(fark)}"
                            else:
                                kapanan = min(e_eksik, fark)
                                y_eksik = e_eksik - kapanan
                                tip = "EKSİK TAMAMLAMA (GİRİŞ)" if kapanan > 0 else "SAYIM FAZLASI (GİRİŞ)"
                                acik = f"Kapanan eksik: {kapanan}" if kapanan > 0 else "Fazla miktar"
                            supabase.table(aktif_tablo).update({"miktar": y_m, "sayim_eksigi": y_eksik}).eq("id", u_id).execute()
                            log_kaydet(st.session_state['kullanici'], tip, row['Ürün Adı'], abs(fark), acik)
                        st.success("✅ Sayım işlendi!")
                        st.rerun()

    with sekme6:
        st.subheader("⚡ Hızlı İşlem")
        aranan = st.text_input("🔍 Stok Numarası:")
        if aranan and not df.empty:
            eslesen = df[df['Stok No'].astype(str).str.strip() == aranan.strip()]
            if not eslesen.empty:
                u = eslesen.iloc[0]
                st.info(f"📦 {u['Ürün Adı']} (Mevcut: {u['Miktar']})")
                with st.form("hizli_form"):
                    mdus = st.number_input("➖ Çıkar:", min_value=0, step=1)
                    mekle = st.number_input("➕ Ekle:", min_value=0, step=1)
                    if st.form_submit_button("💾 Güncelle"):
                        if mdus > 0 or mekle > 0:
                            y_m = int(u['Miktar']) - mdus + mekle
                            supabase.table(aktif_tablo).update({"miktar": y_m}).eq("id", int(u['ID'])).execute()
                            if mdus > 0: log_kaydet(st.session_state['kullanici'], "ÇIKIŞ", u['Ürün Adı'], mdus, "Hızlı")
                            if mekle > 0: log_kaydet(st.session_state['kullanici'], "GİRİŞ", u['Ürün Adı'], mekle, "Hızlı")
                            st.success("Güncellendi!")
                            st.rerun()
            else: st.error("Ürün bulunamadı.")

    with sekme4:
        st.subheader("🪪 Raf Etiketleri (QR & Çizgili Barkod)")
        if not df.empty:
            sec = st.selectbox("Seç:", df['ID'].astype(str) + " - " + df['Ürün Adı'])
            ub = df[df['ID'] == int(sec.split(" - ")[0])].iloc[0]
            st.image(qr_olustur(f"Ürün: {ub['Ürün Adı']}\nStok No: {ub['Stok No']}"), width=150)
            b_bytes = barkod_olustur(ub['Stok No'])
            if b_bytes: st.image(b_bytes, width=250)
            
            html = "<html><head><meta charset='utf-8'><style>.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:15px;}.card{border:2px solid #333;padding:10px;text-align:center;background:#fff;color:#000;}img{max-width:120px;display:block;margin:auto;}</style></head><body><h2>Etiketler</h2><div class='grid'>"
            for _, r in df.iterrows():
                q = base64.b64encode(qr_olustur(f"Ürün: {r['Ürün Adı']}\nStok No: {r['Stok No']}")).decode()
                b = barkod_olustur(r['Stok No'])
                b_b64 = base64.b64encode(b).decode() if b else ""
                html += f"<div class='card'><b>{r['Ürün Adı']}</b><br><small>{r['Stok No']}</small><img src='data:image/png;base64,{q}'>"
                if b_b64: html += f"<img src='data:image/png;base64,{b_b64}'>"
                html += "</div>"
            html += "</div></body></html>"
            st.download_button("📄 Toplu A4 Etiket İndir", data=html, file_name="Etiketler.html", mime="text/html", use_container_width=True)

    with sekme5:
        st.subheader("📝 Hareket Geçmişi")
        df_g = hareketleri_getir()
        if not df_g.empty:
            st.dataframe(df_g, use_container_width=True, hide_index=True)
            st.download_button("📥 Excel İndir", data=df_g.to_csv(index=False).encode('utf-8-sig'), file_name="Gecmis.csv", mime='text/csv')
        else: st.info("Kayıt yok.")

    with sekme7:
        st.subheader("📑 Sözleşme Takibi")
        if not df.empty and 'Alım Türü' in df.columns:
            dp = df[df['Alım Türü'] == 'Piyasa Alımı']
            if not dp.empty: st.dataframe(dp[['Sözleşme No', 'Ürün Adı', 'Miktar', 'Birim', 'Sözleşme Kritik', 'Sözleşme Tarihi', 'Sözleşme Bitiş Tarihi']], use_container_width=True, hide_index=True)
            else: st.info("Sözleşmeli alım yok.")

    with sekme8:
        st.subheader("💬 Geri Bildirim")
        with st.form("gb"):
            tur = st.selectbox("Tür", ["Hata", "Talep"])
            msj = st.text_area("Mesajınız:")
            if st.form_submit_button("Gönder") and msj.strip():
                supabase.table('geri_bildirimler').insert({"kullanici": st.session_state['kullanici'], "tur": tur, "mesaj": msj, "firma": st.session_state['firma']}).execute()
                st.success("Gönderildi!")
        if st.session_state['rol'] == 'admin':
            res_gb = supabase.table('geri_bildirimler').select("*").execute()
            if res_gb.data: st.dataframe(tablo_isimleri_degistir(pd.DataFrame(res_gb.data)), use_container_width=True, hide_index=True)

    with sekme11:
        st.subheader("📂 Akıllı Toplu Çıkış")
        upl = st.file_uploader("Dosya Yükle", type=['xlsx', 'csv'])
        if upl:
            df_y = pd.read_csv(upl) if upl.name.endswith('.csv') else pd.read_excel(upl)
            c1, c2 = st.columns(2)
            stok_s = c1.selectbox("Stok No Sütunu", df_y.columns)
            mik_s = c2.selectbox("Miktar Sütunu", df_y.columns)
            if st.button("İşlemi Onayla"):
                for _, r in df_y.iterrows():
                    sno = str(r[stok_s]).strip()
                    dus = rakam_temizle(r[mik_s])
                    es = df[df['Stok No'].astype(str).str.strip() == sno]
                    if not es.empty and dus > 0:
                        mev = float(es.iloc[0]['Miktar'])
                        supabase.table(aktif_tablo).update({"miktar": mev - dus}).eq("id", int(es.iloc[0]['ID'])).execute()
                        log_kaydet(st.session_state['kullanici'], "ÇIKIŞ", es.iloc[0]['Ürün Adı'], dus, "Toplu çıkış")
                st.success("✅ Tamamlandı!")
                st.rerun()

    if st.session_state['rol'] == 'admin':
        with sekme9:
            st.subheader("👥 Kullanıcı Yönetimi")
            with st.form("yk"):
                k = st.text_input("Kullanıcı Adı")
                s = st.text_input("Geçici Şifre", type="password")
                y = st.selectbox("Yetki", ["Gida", "Temizlik", "Yonetici"])
                f = st.text_input("Firma / Birlik Adı")
                if st.form_submit_button("Oluştur"):
                    if k and s and f:
                        supabase.table('kullanicilar').insert({"kullanici_adi": k, "sifre": sifre_hashle(s), "yetki": y, "firma": f, "ilk_giris": "Evet", "son_guncelleme": bugun.strftime('%Y-%m-%d')}).execute()
                        st.success("✅ Kullanıcı eklendi.")

        with sekme10:
            st.subheader("📢 Duyuru")
            res_d = supabase.table('duyurular').select("*").execute()
            m_val = res_d.data[0]['mesaj'] if res_d.data else ""
            a_val = str(res_d.data[0].get('aktif', '')) == 'Evet' if res_d.data else False
            with st.form("duy"):
                dm = st.text_area("Metin", value=m_val)
                da = st.checkbox("Aktif", value=a_val)
                if st.form_submit_button("Kaydet"):
                    durum = "Evet" if da else "Hayır"
                    if not res_d.data: supabase.table('duyurular').insert({"mesaj": dm, "aktif": durum}).execute()
                    else: supabase.table('duyurular').update({"mesaj": dm, "aktif": durum}).eq("id", res_d.data[0]['id']).execute()
                    st.success("Kaydedildi!")
                    st.rerun()
