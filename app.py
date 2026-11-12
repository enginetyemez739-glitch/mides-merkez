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
import schedule
import time
import threading
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
    st.error(f"⚠️ Supabase bağlantı kurulum hatası: {e}")
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

def telegram_mesaj_gonder_tokenli(token, chat_id, mesaj):
    if token and chat_id and str(token).lower() != "nan" and str(chat_id).lower() != "nan":
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": mesaj}
        try: requests.post(url, data=payload)
        except: pass

def telegram_mesaj_gonder(mesaj):
    if 'telegram_token' in st.session_state and 'telegram_chat_id' in st.session_state:
        telegram_mesaj_gonder_tokenli(st.session_state['telegram_token'], st.session_state['telegram_chat_id'], mesaj)

# --- OTOMATİK ZAMANLAYICI (HER GÜN SAAT 08:00) ---
def otomatik_0800_kontrol_islevi():
    try:
        bugun = datetime.now(TR_TZ).date()
        for tablo in ['gida_deposu', 'temizlik_deposu']:
            res = supabase.table(tablo).select("*").execute()
            if not res.data: continue
            df_auto = pd.DataFrame(res.data)
            df_auto = tablo_isimleri_degistir(df_auto)
            
            rapor = f"⏰ OTOMATİK 08:00 RAPORU ({tablo.upper()})\n\n"
            kurtarici = 0
            for _, row in df_auto.iterrows():
                u_adi = str(row.get('Ürün Adı', ''))
                mik = float(row.get('Miktar', 0) or 0)
                krit = float(row.get('Kritik Stok', 10) or 10)
                skt_str = str(row.get('SKT', ''))
                
                if mik <= krit:
                    rapor += f"📉 ALARM: {u_adi} (Kalan: {mik})\n"
                    kurtarici += 1
                try:
                    if skt_str and skt_str != "-":
                        skt_tarih = datetime.strptime(skt_str, '%Y-%m-%d').date()
                        kalan_gun = (skt_tarih - bugun).days
                        if kalan_gun <= 30:
                            rapor += f"⚠️ SKT UYARI: {u_adi} ({kalan_gun} gün kaldı)\n"
                            kurtarici += 1
                except: pass
                
            if kurtarici > 0:
                k_res = supabase.table('kullanicilar').select("telegram_token, chat_id, firma").execute()
                if k_res.data:
                    for k in k_res.data:
                        t_token = k.get('telegram_token')
                        t_chat = k.get('chat_id')
                        if t_token and t_chat:
                            telegram_mesaj_gonder_tokenli(t_token, t_chat, rapor)
    except Exception as e:
        print(f"Zamanlayıcı Hatası: {e}")

@st.cache_resource
def arka_plan_zamanlayici_baslat():
    # Sunucu UTC olduğu için Türkiye saati 08:00 = UTC 05:00'dır.
    schedule.every().day.at("05:00").do(otomatik_0800_kontrol_islevi)
    
    def run_schedule():
        while True:
            schedule.run_pending()
            time.sleep(60)
            
    t = threading.Thread(target=run_schedule, daemon=True)
    t.start()
    return True

# Sistemi kaç kişi açarsa açsın, bu komut sunucuda sadece 1 kez çalışır.
arka_plan_zamanlayici_baslat()


# --- OTURUM YÖNETİMİ ---
if 'giris_yapildi' not in st.session_state:
    st.session_state.update({
        'giris_yapildi': False, 'kullanici': "", 'rol': "", 'firma': "", 
        'sifre_degistirme_modu': False, 'ilk_giris_uyarisi': False, 'telegram_ayar_modu': False
    })

try:
    kullanicilar_res = supabase.table('kullanicilar').select("*").execute()
    df_kullanicilar = tablo_isimleri_degistir(pd.DataFrame(kullanicilar_res.data)) if kullanicilar_res.data else pd.DataFrame()
except Exception as e:
    st.error(f"🚨 Supabase bağlantı hatası: {e}")
    st.stop()

# TELEGRAM REHBER METNİ
telegram_rehber_html = """
<details>
<summary><b>📖 Telegram Token ve Chat ID Nasıl Alınır? (İsteğe Bağlı)</b></summary>
<p>
Telegram kullanan personeller bildirim alabilmek için doldurabilir, zorunlu değildir:<br>
1. <b>Bot Oluşturma:</b> Telegram'da <b>@BotFather</b> aratın, <code>/start</code> yazın, ardından <code>/newbot</code> komutunu gönderip bir isim verin. BotFather size bir <b>Token</b> verecektir.<br>
2. <b>Sohbeti Başlatma:</b> Oluşturduğunuz botunuzu aratıp açın ve <b>Start</b> butonuna basın.<br>
3. <b>Chat ID Öğrenme:</b> Telegram'da <b>@userinfobot</b> aratın ve sohbeti başlatın, size vereceği rakam sizin <b>Chat ID</b>'nizdir.
</p>
</details>
"""

# 1. İLK GİRİŞTE SADECE ŞİFRE DEĞİŞTİRME (ZORUNLU)
if st.session_state['sifre_degistirme_modu']:
    if st.session_state.get('ilk_giris_uyarisi'): 
        st.warning("⚠️ Sisteme ilk girişiniz! Lütfen devam etmek için kendi güvenli şifrenizi belirleyin.")
    else: 
        st.warning("⚠️ Şifrenizin kullanım süresi dolmuş. Lütfen yeni şifre belirleyin.")
        
    with st.form("ilk_sifre_formu"):
        yeni_sifre = st.text_input("Yeni Şifre:", type="password")
        yeni_sifre_tekrar = st.text_input("Yeni Şifre (Tekrar):", type="password")
        
        if st.form_submit_button("Şifreyi Kaydet ve Devam Et"):
            if yeni_sifre == yeni_sifre_tekrar and len(yeni_sifre) >= 4:
                kullanici_id = int(df_kullanicilar[df_kullanicilar['Kullanıcı Adı'] == st.session_state['kullanici']].iloc[0]['ID'])
                bugun = datetime.now(TR_TZ).strftime('%Y-%m-%d')
                
                supabase.table('kullanicilar').update({
                    "sifre": sifre_hashle(yeni_sifre), 
                    "son_guncelleme": bugun, 
                    "ilk_giris": "Hayır"
                }).eq("id", kullanici_id).execute()
                
                st.success("✅ Şifreniz başarıyla kaydedildi!")
                st.session_state.update({
                    'sifre_degistirme_modu': False, 'giris_yapildi': True, 'ilk_giris_uyarisi': False
                })
                time.sleep(1)
                st.rerun()
            else: 
                st.error("Şifreler uyuşmuyor veya çok kısa (en az 4 karakter olmalı).")
    st.stop()

# 2. İSTEDİĞİ ZAMAN AÇIP TELEGRAM AYARLAYABİLECEĞİ EKRAN (OPSİYONEL)
if st.session_state.get('telegram_ayar_modu'):
    st.info("📱 Telegram Bildirim Ayarlarınızı Yapılandırın (Zorunlu Değildir)")
    with st.form("telegram_ayar_formu"):
        st.markdown(telegram_rehber_html, unsafe_allow_html=True)
        
        mevcut_k = df_kullanicilar[df_kullanicilar['Kullanıcı Adı'] == st.session_state['kullanici']]
        esk_token = str(mevcut_k.iloc[0].get('Telegram Token', '')) if not mevcut_k.empty else ""
        esk_chat = str(mevcut_k.iloc[0].get('Chat ID', '')) if not mevcut_k.empty else ""
        if esk_token == "nan": esk_token = ""
        if esk_chat == "nan": esk_chat = ""

        girilen_token = st.text_input("Telegram Bot Token (Boş bırakabilirsiniz):", value=esk_token)
        girilen_chat = st.text_input("Telegram Chat ID (Boş bırakabilirsiniz):", value=esk_chat)
        
        c_t1, c_t2 = st.columns(2)
        if c_t1.form_submit_button("💾 Telegram Bilgilerini Kaydet"):
            kullanici_id = int(df_kullanicilar[df_kullanicilar['Kullanıcı Adı'] == st.session_state['kullanici']].iloc[0]['ID'])
            supabase.table('kullanicilar').update({
                "telegram_token": girilen_token.strip(),
                "chat_id": girilen_chat.strip()
            }).eq("id", kullanici_id).execute()
            
            st.session_state['telegram_token'] = girilen_token.strip()
            st.session_state['telegram_chat_id'] = girilen_chat.strip()
            st.success("✅ Telegram ayarları güncellendi!")
            st.session_state['telegram_ayar_modu'] = False
            time.sleep(1)
            st.rerun()
            
        if c_t2.form_submit_button("❌ Geri Dön"):
            st.session_state['telegram_ayar_modu'] = False
            st.rerun()
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
                        
                        if yetki in ["yonetici", "yönetici", "merkez yönetici"]: st.session_state['rol'] = "admin"
                        elif yetki in ["gida", "gıda"]: st.session_state['rol'] = "gida"
                        else: st.session_state['rol'] = "temizlik"
                        
                        st.session_state['telegram_token'] = str(kullanici['Telegram Token'].values[0]) if 'Telegram Token' in kullanici else ""
                        st.session_state['telegram_chat_id'] = str(kullanici['Chat ID'].values[0]) if 'Chat ID' in kullanici else ""
                        
                        ilk_giris = str(kullanici['İlk Giriş'].values[0]).strip().lower() if 'İlk Giriş' in kullanici else "hayır"
                        if ilk_giris == "evet":
                            st.session_state['sifre_degistirme_modu'] = True
                            st.session_state['ilk_giris_uyarisi'] = True
                            st.rerun()
                        else:
                            son_guncelleme = pd.to_datetime(kullanici['Son Güncelleme'].values[0], errors='coerce')
                            if (datetime.now(TR_TZ).replace(tzinfo=None) - son_guncelleme).days >= 90: 
                                st.session_state['sifre_degistirme_modu'] = True
                            else:
                                st.session_state['giris_yapildi'] = True
                                st.rerun()
                    else: st.error("❌ Bu sisteme giriş yetkiniz bulunmamaktadır!")
            else: st.error("❌ Kullanıcı adı veya şifre hatalı!")
else:
    # --- ANA ARAYÜZ ---
    if st.session_state['rol'] == 'admin':
        st.info("👑 **Merkezi Yönetici Modu:** Tüm yetkilere sahipsiniz.")
        secilen_depo = st.selectbox("Aktif Depo", ["🍎 Gıda Deposu", "🧹 Temizlik Deposu"])
        aktif_tablo = "gida_deposu" if "Gıda" in secilen_depo else "temizlik_deposu"
        depo_adi = "Gıda Deposu" if "Gıda" in secilen_depo else "Temizlik Deposu"
    else:
        if st.session_state['rol'] == 'gida':
            aktif_tablo = "gida_deposu"
            depo_adi = "Gıda Deposu"
        else:
            aktif_tablo = "temizlik_deposu"
            depo_adi = "Temizlik Deposu"

    df = verileri_getir(aktif_tablo)
    if not df.empty and 'Sayım Eksiği' not in df.columns:
        df['Sayım Eksiği'] = 0.0
    if not df.empty:
        df['Sayım Eksiği'] = pd.to_numeric(df['Sayım Eksiği'], errors='coerce').fillna(0)
        
    bugun = datetime.now(TR_TZ).date()
                        
    c_ust1, c_ust2 = st.columns([3, 2])
    with c_ust1: st.title(f"📦 {st.session_state['firma']} - {depo_adi}")
    with c_ust2:
        st.write(f"👤 {st.session_state['kullanici']} ({'Merkez Yönetici' if st.session_state['rol'] == 'admin' else 'Firma Yetkilisi'})")
        
        # ÜST BUTONLAR
        b_col1, b_col2, b_col3 = st.columns(3)
        if b_col1.button("🔄 Şifre Değiştir"):
            st.session_state['sifre_degistirme_modu'] = True
            st.rerun()
        if b_col2.button("📱 Telegram Ayarları"):
            st.session_state['telegram_ayar_modu'] = True
            st.rerun()
        if b_col3.button("🚪 Çıkış Yap"):
            st.session_state['giris_yapildi'] = False
            st.rerun()

    # Duyurular
    try:
        res_duyuru = supabase.table('duyurular').select("*").execute()
        if res_duyuru.data:
            aktif_duyuru = str(res_duyuru.data[0].get('aktif', 'Hayır'))
            duyuru_mesaji = str(res_duyuru.data[0].get('mesaj', ''))
            if aktif_duyuru == 'Evet' and duyuru_mesaji.strip(): st.warning(f"📢 **SİSTEM DUYURUSU:** {duyuru_mesaji}")
    except Exception:
        pass

    if st.session_state['rol'] == 'admin':
        sekme1, sekme2, sekme3, sekme12, sekme6, sekme4, sekme5, sekme7, sekme8, sekme9, sekme10, sekme11 = st.tabs(["📊 Özet & Analiz", "➕ Ürün Ekle", "🔄 Güncelle / Sil", "📋 Depo Sayımı", "⚡ Hızlı İşlem", "🪪 Ürün Kartı", "📝 Geçmiş İşlemler", "📑 Sözleşmeler", "💬 Bildirimler", "👥 Kullanıcı Yönetimi", "📢 Duyuru", "📂 Toplu Çıkış"])
    else:
        sekme1, sekme2, sekme3, sekme12, sekme6, sekme4, sekme5, sekme7, sekme8, sekme11 = st.tabs(["📊 Özet", "➕ Ürün Ekle", "🔄 Güncelle / Sil", "📋 Depo Sayımı", "⚡ Hızlı İşlem", "🪪 Ürün Kartı", "📝 Depo Geçmişi", "📑 Sözleşmeler", "💬 Geri Bildirim", "📂 Toplu Çıkış"])

    with sekme1:
        st.markdown(f"### 📋 Uyarılar")
        krt_sayisi = 0
        telegram_raporu = f"⚠️ {st.session_state['firma']} - {depo_adi.upper()} UYARI RAPORU ⚠️\n\n"
        
        if not df.empty:
            for index, row in df.iterrows():
                urun_adi = str(row.get('Ürün Adı', 'Bilinmeyen Ürün')).strip()
                stok_no = str(row.get('Stok No', '-'))
                miktar_metni = str(row.get('Miktar', '0')).strip()
                birim = str(row.get('Birim', '')).strip()
                try:
                    skt_metni = str(row.get('SKT', '')).strip()
                    if skt_metni and skt_metni != "-" and skt_metni.lower() != "nan":
                        skt = datetime.strptime(skt_metni, '%Y-%m-%d').date()
                        kalan = (skt - bugun).days
                        uyari_baslik = f"{urun_adi} (Stok No: {stok_no} | {miktar_metni} {birim})"
                        if kalan < 0:
                            st.error(f"❌ {uyari_baslik} - TARİHİ GEÇTİ! ({skt_metni})")
                            telegram_raporu += f"❌ {uyari_baslik} - TARİHİ GEÇTİ!\n"
                            krt_sayisi += 1
                        elif 0 <= kalan <= 30:
                            st.warning(f"⚠️ {uyari_baslik} - SKT'ye {kalan} gün kaldı! ({skt_metni})")
                            telegram_raporu += f"⚠️ {uyari_baslik} - {kalan} gün kaldı!\n"
                            krt_sayisi += 1
                except: pass
                try:
                    kritik_metni = str(row.get('Kritik Stok', '10')).strip()
                    if not miktar_metni or miktar_metni.lower() == "nan": miktar_metni = "0"
                    if not kritik_metni or kritik_metni.lower() == "nan": kritik_metni = "10"
                    if float(miktar_metni) <= float(kritik_metni):
                        st.error(f"📉 STOK ALARMI: {urun_adi} bitmek üzere! (Kalan: {int(float(miktar_metni))} {birim})")
                        telegram_raporu += f"📉 ALARM: {urun_adi} (Kalan: {int(float(miktar_metni))} {birim})\n"
                        krt_sayisi += 1
                except: pass

        if krt_sayisi == 0: st.success("✅ Depo durumu çok iyi. Tarihi yaklaşan veya stoğu tükenen ürün yok.")
        
        if st.button("📲 Telegram'a Manuel Rapor Gönder"):
            telegram_mesaj_gonder(telegram_raporu)
            st.toast("✅ Telegram'a Gönderildi!")
            
        st.divider()
        st.markdown("### 📦 Stok Numarasına Göre Genel Toplamlar")
        if not df.empty:
            try:
                df['Miktar_Sayi'] = pd.to_numeric(df['Miktar'], errors='coerce').fillna(0)
                toplam_stok_df = df.groupby('Stok No').agg({'Ürün Adı': 'first', 'Miktar_Sayi': 'sum', 'Birim': 'first'}).reset_index()
                toplam_stok_df.rename(columns={'Miktar_Sayi': 'Toplam Miktar'}, inplace=True)
                st.dataframe(toplam_stok_df[['Stok No', 'Ürün Adı', 'Toplam Miktar', 'Birim']], use_container_width=True, hide_index=True)
            except: st.info("Toplamlar hesaplanırken hata oluştu.")

            st.markdown("### 🔍 Detaylı Parti Listesi")
            gosterilecek_df = df.drop(columns=['Resim Yolu', 'Miktar_Sayi', 'Depo Sahibi', 'Firma'], errors='ignore')
            st.dataframe(gosterilecek_df, use_container_width=True, hide_index=True)
        else:
            st.info("Depoda henüz ürün bulunmamaktadır.")

        if st.session_state['rol'] == 'admin':
            st.divider()
            st.markdown("### 📈 Firma Aktiflik ve Performans Analizi")
            df_perf = hareketleri_getir()
            if not df_perf.empty and 'Firma' in df_perf.columns:
                c_g1, c_g2 = st.columns(2)
                with c_g1:
                    st.markdown("**Firmalara Göre Toplam İşlem Hacmi**")
                    st.bar_chart(df_perf['Firma'].value_counts())
                with c_g2:
                    st.markdown("**Firmaların Son Görülme Zamanları**")
                    son_gorme = df_perf.groupby('Firma')['Tarih'].max().reset_index()
                    son_gorme.columns = ['Firma', 'Son İşlem Tarihi']
                    st.dataframe(son_gorme.sort_values('Son İşlem Tarihi', ascending=False), use_container_width=True, hide_index=True)

    with sekme2:
        st.subheader("➕ Depoya Yeni Ürün Ekle")
        ekleme_yontemi = st.radio("Ürün Ekleme Yöntemi Seçiniz:", ["📝 Manuel Form ile Tek Tek Ekle", "📸 Yapay Zeka ile İrsaliye/Fatura Okut (Toplu Ekle)"], horizontal=True)

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
                    kritik_seviye = st.number_input("Depo Kritik Uyarı Seviyesi", min_value=1, value=20)
                    uretim_tarihi = st.date_input("Üretim Tarihi")
                    skt = st.date_input("Son Kullanma Tarihi (SKT)")
                    st.markdown("---")
                    sozlesme_no = st.text_input("Sözleşme No (Sadece Piyasa Alımı İçin)")
                    sozlesme_tarihi = st.date_input("Sözleşme Tarihi")
                    sozlesme_bitis = st.date_input("Sözleşme Bitiş Tarihi")
                    sozlesme_kritik = st.number_input("Sözleşme / Yıllık Kritik Sınırı", min_value=0.0, value=20.0, step=1.0)
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
                        "sayim_eksigi": 0,
                        "firma": st.session_state['firma']
                    }
                    supabase.table(aktif_tablo).insert(yeni_veri).execute()
                    log_kaydet(st.session_state['kullanici'], "YENİ KAYIT", urun_adi, miktar, f"{alim_turu} ile eklendi")
                    st.success(f"✅ Ürün depoya başarıyla kaydedildi!")
                    st.rerun()
                else: st.error("Lütfen Stok Numarası ve Ürün Adı alanlarını doldurunuz.")
        else:
            st.info("💡 **Akıllı Mal Kabul:** Gelen ürünlerin irsaliyesini, faturasını veya listesini fotoğraflayın. Yapay zeka tüm listeyi sizin için saniyeler içinde okuyup tabloya dönüştürecektir.")
            resim_dosyasi_giris = st.file_uploader("Fatura / Liste Fotoğrafı Yükleyin", type=['jpg', 'jpeg', 'png'], key="giris_foto")

            if resim_dosyasi_giris:
                if st.button("🤖 Yapay Zekaya Okut ve Listeyi Çıkar"):
                    with st.spinner("Yapay Zeka fatura/listeyi inceliyor, lütfen bekleyin..."):
                        try:
                            gemini_api_key = st.secrets.get("GEMINI_API_KEY", "").strip()
                            if not gemini_api_key:
                                st.error("❌ Gemini API Anahtarı bulunamadı!")
                            else:
                                genai.configure(api_key=gemini_api_key)
                                model = genai.GenerativeModel('gemini-3.5-flash')
                                prompt = """Sen uzman bir depo mal kabul asistanısın. Gönderdiğim fotoğrafta depoya giren ürünlerin bir faturası, irsaliyesi veya listesi bulunuyor. Tablodaki ürünleri oku ve her bir satır için sadece şu bilgileri çıkar: 
                                - 'Stok No' (eğer belgede barkod/kod yoksa tamamen boş bırak), 
                                - 'Ürün Adı', 
                                - 'Miktar' (sadece rakam),
                                - 'Birim' (Kg, Litre, Adet vb.). 
                                Bana SADECE geçerli bir JSON dizisi döndür, başka hiçbir metin veya açıklama ekleme. 
                                Örnek Format: [{"Stok No": "8920270048540", "Ürün Adı": "Domates Salçası", "Miktar": "50", "Birim": "Kg"}]"""
                                img = Image.open(resim_dosyasi_giris)
                                response = model.generate_content([prompt, img])

                                json_text = response.text.strip()
                                if json_text.startswith("```json"): json_text = json_text.replace("```json", "").replace("```", "").strip()
                                elif json_text.startswith("```"): json_text = json_text.replace("```", "").strip()

                                ai_data = json.loads(json_text)
                                st.session_state['ai_giris_df'] = pd.DataFrame(ai_data)
                                st.success("✅ Belge başarıyla okundu! Lütfen aşağıdaki tablodan verileri kontrol edip onaylayın.")
                        except Exception as e:
                            st.error(f"Sistem Hatası Detayı (Lütfen daha net bir fotoğraf deneyin): {str(e)}")

            if 'ai_giris_df' in st.session_state and st.session_state['ai_giris_df'] is not None:
                st.markdown("### 🔍 Okunan Ürünleri Düzenle ve Onayla")
                st.warning("⚠️ Lütfen 'Stok No'su boş gelen ürünlere benzersiz bir numara yazın. Ayrıca sağ taraftan ürünlerin SKT'sini (Son Kullanma Tarihi) ayarlamayı unutmayın.")
                
                temp_df = st.session_state['ai_giris_df'].copy()
                if 'SKT' not in temp_df.columns:
                    temp_df['SKT'] = bugun.strftime('%Y-%m-%d')
                if 'Kritik Stok' not in temp_df.columns:
                    temp_df['Kritik Stok'] = 10
                
                with st.form("toplu_giris_onay"):
                    duzenlenmis_giris = st.data_editor(temp_df, use_container_width=True, hide_index=True)
                    
                    c_btn1, c_btn2 = st.columns(2)
                    submit_kaydet = c_btn1.form_submit_button("💾 Seçili Ürünleri Depoya Ekle")
                    submit_iptal = c_btn2.form_submit_button("❌ Listeyi İptal Et / Temizle")
                    
                    if submit_iptal:
                        st.session_state['ai_giris_df'] = None
                        st.rerun()

                    if submit_kaydet:
                        zaman, k_adi, f_adi = datetime.now(TR_TZ).strftime('%Y-%m-%d'), st.session_state['kullanici'], st.session_state.get('firma', '')
                        eklenen_sayisi = 0
                        
                        for i, r in duzenlenmis_giris.iterrows():
                            s_no = str(r.get('Stok No', '')).strip()
                            u_adi = str(r.get('Ürün Adı', '')).strip()
                            miktar_val = float(r.get('Miktar', 0) or 0)
                            birim_val = str(r.get('Birim', 'Adet')).strip()
                            skt_val = str(r.get('SKT', zaman)).strip()
                            kritik_val = int(float(r.get('Kritik Stok', 10) or 10))
                            
                            if u_adi and miktar_val > 0 and s_no and s_no != "None" and s_no != "nan":
                                mevcut_urun = pd.DataFrame()
                                if not df.empty:
                                    mevcut_urun = df[df['Stok No'].astype(str).str.strip() == s_no]
                                
                                if not mevcut_urun.empty:
                                    eski_miktar = float(mevcut_urun.iloc[0]['Miktar'])
                                    yeni_miktar = eski_miktar + miktar_val
                                    urun_id = int(mevcut_urun.iloc[0]['ID'])
                                    supabase.table(aktif_tablo).update({"miktar": yeni_miktar, "skt": skt_val}).eq("id", urun_id).execute()
                                    log_kaydet(k_adi, "GİRİŞ", u_adi, miktar_val, "Yapay Zeka Toplu Ekleme")
                                else:
                                    yeni_veri = {
                                        "stok_no": s_no, "urun_adi": u_adi, "miktar": miktar_val, "birim": birim_val,
                                        "eklenme_tarihi": zaman, "skt": skt_val, "uretim_tarihi": zaman,
                                        "giris_tarihi": zaman, "resim_yolu": "", "kritik_stok": kritik_val,
                                        "alim_turu": "Merkezi Alım", "sozlesme_no": "-", "sozlesme_tarihi": "-",
                                        "sozlesme_bitis_tarihi": "-", "sozlesme_kritik": 0.0, "sayim_eksigi": 0, "firma": f_adi
                                    }
                                    supabase.table(aktif_tablo).insert(yeni_veri).execute()
                                    log_kaydet(k_adi, "YENİ KAYIT", u_adi, miktar_val, "Yapay Zeka Toplu Ekleme")
                                eklenen_sayisi += 1
                        
                        if eklenen_sayisi > 0:
                            st.session_state['ai_giris_df'] = None
                            st.success(f"✅ Harika! Toplam {eklenen_sayisi} kalem ürün deponuza başarıyla eklendi.")
                            st.rerun()
                        else:
                            st.error("Hiçbir ürün eklenmedi. Lütfen ürünlerin Stok Numaralarının dolu olduğundan emin olun.")

    with sekme3:
        st.subheader("🔄 Ürün Bilgilerini Güncelle ve Sil")
        if not df.empty:
            secili_guncelleme = st.selectbox("İşlem yapılacak ürünü seçin:", df['ID'].astype(str) + " - " + df['Ürün Adı'])
            secili_id = int(secili_guncelleme.split(" - ")[0])
            urun = df[df['ID'] == secili_id].iloc[0]
            urun_miktar = int(float(str(urun.get('Miktar', '0')).strip() or '0'))
            with st.form("guncelleme_formu"):
                c_g1, c_g2 = st.columns(2)
                with c_g1:
                    yeni_stok = st.text_input("Stok No:", value=str(urun.get('Stok No', '')))
                    cikis = st.number_input("➖ Çıkış:", min_value=0, max_value=urun_miktar, step=1)
                    giris = st.number_input("➕ Giriş:", min_value=0, step=1)
                with c_g2:
                    try: skt_val = datetime.strptime(str(urun.get('SKT', '')).strip(), '%Y-%m-%d').date()
                    except: skt_val = bugun
                    y_skt = st.date_input("SKT:", value=skt_val)
                    y_kritik = st.number_input("Depo Kritik Sınır:", value=int(float(str(urun.get('Kritik Stok', '10')).strip() or '10')), step=1)
                c_btn1, c_btn2 = st.columns(2)
                if c_btn1.form_submit_button("💾 Güncellemeyi Kaydet"):
                    yeni_miktar = urun_miktar - cikis + giris
                    supabase.table(aktif_tablo).update({
                        "stok_no": yeni_stok, "miktar": yeni_miktar, "skt": y_skt.strftime('%Y-%m-%d'), "kritik_stok": y_kritik
                    }).eq("id", secili_id).execute()
                    
                    if cikis > 0: log_kaydet(st.session_state['kullanici'], "ÇIKIŞ", urun['Ürün Adı'], cikis, "Manuel Güncelleme")
                    if giris > 0: log_kaydet(st.session_state['kullanici'], "GİRİŞ", urun['Ürün Adı'], giris, "Manuel Güncelleme")
                    st.success("Güncellendi!")
                    st.rerun()
                if c_btn2.form_submit_button("🗑️ Ürünü Depodan Tamamen Sil"):
                    supabase.table(aktif_tablo).delete().eq("id", secili_id).execute()
                    log_kaydet(st.session_state['kullanici'], "SİLME", urun['Ürün Adı'], urun_miktar, "Ürün tamamen silindi")
                    st.success(f"🗑️ Ürün depodan silindi!")
                    st.rerun()

    # GELİŞTİRİLMİŞ SAYIM VE EKSİK TAKİP MODÜLÜ
    with sekme12:
        st.subheader("📋 Depo Sayımı ve Kalıcı Eksik Takibi")
        
        if not df.empty:
            eksikler_df = df[df['Sayım Eksiği'] > 0]
            if not eksikler_df.empty:
                st.error("🚨 **DİKKAT - GEÇMİŞTEN KALAN EKSİKLER:** Aşağıdaki ürünler önceki sayımlarda eksik çıkmıştır ve henüz depoda bulunamamış/tamamlanmamıştır.")
                st.dataframe(eksikler_df[['Stok No', 'Ürün Adı', 'Sayım Eksiği', 'Birim']], hide_index=True, use_container_width=True)
                st.divider()

            st.info("Raflardaki gerçek ürün sayılarını girin. Eksik çıkarsa 'Sayım Eksiği' olarak kalıcı kaydedilir. Eğer geçmişteki eksik ürünü bulup fazla girerseniz, eksik borcunuz otomatik kapanır.")
            
            sayim_df = df[['ID', 'Stok No', 'Ürün Adı', 'Miktar', 'Sayım Eksiği', 'Birim']].copy()
            sayim_df.rename(columns={'Miktar': 'Sistemdeki Miktar', 'Sayım Eksiği': 'Bilinen Eksik Miktar'}, inplace=True)
            sayim_df['Raftaki Gerçek Sayı'] = sayim_df['Sistemdeki Miktar']
            
            with st.form("sayim_formu"):
                st.markdown("### 🔢 Fiziki Sayım Tablosu")
                duzenlenmis_sayim = st.data_editor(
                    sayim_df,
                    column_config={
                        "Raftaki Gerçek Sayı": st.column_config.NumberColumn("✏️ Raftaki Gerçek Sayı", min_value=0.0, step=1.0)
                    },
                    disabled=["ID", "Stok No", "Ürün Adı", "Sistemdeki Miktar", "Bilinen Eksik Miktar", "Birim"],
                    hide_index=True,
                    use_container_width=True
                )
                hesapla_btn = st.form_submit_button("💾 Farkları Hesapla ve Stokları Güncelle")
                
            if hesapla_btn:
                duzenlenmis_sayim['Fark'] = duzenlenmis_sayim['Raftaki Gerçek Sayı'] - duzenlenmis_sayim['Sistemdeki Miktar']
                fark_olanlar = duzenlenmis_sayim[duzenlenmis_sayim['Fark'] != 0].copy()
                
                if fark_olanlar.empty:
                    st.success("✅ Mükemmel! Yaptığınız fiziki sayım ile sistemdeki stoklar birebir eşleşiyor. Yeni bir fark yok.")
                else:
                    st.warning("⚠️ Sayım sonucunda sistem kayıtları ile uyuşmayan ürünler tespit edildi. İlgili ürünlerin stokları ve eksik hafızaları güncellendi!")
                    
                    zaman = datetime.now(TR_TZ).strftime('%Y-%m-%d %H:%M:%S')
                    for _, row in fark_olanlar.iterrows():
                        urun_id = int(row['ID'])
                        yeni_miktar = float(row['Raftaki Gerçek Sayı'])
                        fark = float(row['Fark'])
                        urun_adi = row['Ürün Adı']
                        eski_eksik = float(row['Bilinen Eksik Miktar'])
                        
                        if fark < 0:
                            yeni_eksik = eski_eksik + abs(fark)
                            islem_tipi = "SAYIM EKSİĞİ (ÇIKIŞ)"
                            aciklama = f"Sistem: {row['Sistemdeki Miktar']} | Sayım: {yeni_miktar} | Yeni oluşan eksik: {abs(fark)}"
                        else:
                            kapanan = min(eski_eksik, fark)
                            yeni_eksik = eski_eksik - kapanan
                            if kapanan > 0:
                                islem_tipi = "EKSİK TAMAMLAMA (GİRİŞ)"
                                aciklama = f"Önceki eksiklerden {kapanan} kadarı bulundu/tamamlandı."
                            else:
                                islem_tipi = "SAYIM FAZLASI (GİRİŞ)"
                                aciklama = f"Sistemde {row['Sistemdeki Miktar']} görünüyordu, sayımda {yeni_miktar} (fazla) çıktı."
                        
                        supabase.table(aktif_tablo).update({"miktar": yeni_miktar, "sayim_eksigi": yeni_eksik}).eq("id", urun_id).execute()
                        log_kaydet(st.session_state['kullanici'], islem_tipi, urun_adi, abs(fark), aciklama)
                        
                    st.toast("✅ Veritabanı başarıyla güncellendi!")
                    st.rerun()
        else:
            st.info("Depoda sayım yapılacak ürün bulunmuyor.")

    with sekme6:
        st.subheader("⚡ Hızlı İşlem (Barkod ile)")
        aranan_stok = st.text_input("🔍 Stok Numarasını Yazın:")
        kamera_ac = st.checkbox("📷 QR Okutmak İçin Kamerayı Aç")
        resim = None
        if kamera_ac: resim = st.camera_input("QR Kodu Kameraya Gösterin")
        bulunan = str(aranan_stok).strip() if aranan_stok else None
        if resim:
            cv_img = cv2.cvtColor(np.array(Image.open(resim)), cv2.COLOR_RGB2BGR)
            data, _, _ = cv2.QRCodeDetector().detectAndDecode(cv_img)
            if data:
                try: bulunan = next((s.split("Stok No:")[1].strip() for s in data.split('\n') if "Stok No:" in s), None)
                except: pass
        if bulunan and not df.empty:
            eslesen = df[df['Stok No'].astype(str).str.strip() == bulunan]
            if not eslesen.empty:
                st.info(f"📦 Bulunan Ürün: {eslesen.iloc[0]['Ürün Adı']} (Mevcut: {eslesen.iloc[0]['Miktar']})")
                with st.form("hizli"):
                    m_dus = st.number_input("➖ Çıkar:", min_value=0, step=1)
                    m_ekle = st.number_input("➕ Ekle:", min_value=0, step=1)
                    if st.form_submit_button("💾 Güncelle"):
                        if m_dus > 0 or m_ekle > 0:
                            guncel_id = int(eslesen.iloc[0]['ID'])
                            yeni_m = int(eslesen.iloc[0]['Miktar']) - m_dus + m_ekle
                            supabase.table(aktif_tablo).update({"miktar": yeni_m}).eq("id", guncel_id).execute()
                            
                            if m_dus > 0: log_kaydet(st.session_state['kullanici'], "ÇIKIŞ", eslesen.iloc[0]['Ürün Adı'], m_dus, "Hızlı İşlem")
                            if m_ekle > 0: log_kaydet(st.session_state['kullanici'], "GİRİŞ", eslesen.iloc[0]['Ürün Adı'], m_ekle, "Hızlı İşlem")
                            st.success("Stok güncellendi!")
                            st.rerun()
            else: st.error("❌ Ürün deponuzda bulunamadı.")

    with sekme4:
        st.subheader("🪪 Raf Etiketleri (QR & Çizgili Barkod Birlikte)")
        if not df.empty:
            c_kart1, c_kart2 = st.columns(2)
            with c_kart1:
                st.markdown("**Tekli Ürün Etiketi**")
                secilen = st.selectbox("Etiket Göster:", df['ID'].astype(str) + " - " + df['Ürün Adı'])
                ub = df[df['ID'] == int(secilen.split(" - ")[0])].iloc[0]
                
                qr_bytes = qr_olustur(f"Ürün: {ub['Ürün Adı']}\nStok No: {ub['Stok No']}")
                bar_bytes = barkod_olustur(ub['Stok No'])
                
                st.image(qr_bytes, caption="QR Kod (Kamera için)", width=150)
                if bar_bytes:
                    st.image(bar_bytes, caption=f"Çizgili Barkod ({ub['Stok No']})", width=250)
                    
            with c_kart2:
                st.markdown("**Toplu Raf Etiketleri Çıktısı (A4 Tek Kalemde)**")
                html_icerik = "<html><head><meta charset='utf-8'><style>body { font-family: Arial, sans-serif; } .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; } .card { border: 2px solid #333; padding: 12px; text-align: center; border-radius: 8px; background: #fff; color: #000; } .card img { max-width: 130px; height: auto; margin: 4px auto; display: block; } .title { font-size: 14px; font-weight: bold; margin-bottom: 2px; } .stok { font-size: 12px; color: #555; margin-bottom: 5px; } @media print { .grid { gap: 10px; } .card { page-break-inside: avoid; } }</style></head><body><h2 style='text-align:center;'>MİDES Depo Raf Etiketleri</h2><div class='grid'>"
                
                for _, row in df.iterrows():
                    s_no = str(row.get('Stok No', ''))
                    u_adi = str(row.get('Ürün Adı', ''))
                    q_data = qr_olustur(f"Ürün: {u_adi}\nStok No: {s_no}")
                    b_data = barkod_olustur(s_no)
                    
                    q_b64 = base64.b64encode(q_data).decode()
                    b_b64 = base64.b64encode(b_data).decode() if b_data else ""
                    
                    html_icerik += f"<div class='card'>"
                    html_icerik += f"<div class='title'>{u_adi}</div>"
                    html_icerik += f"<div class='stok'>Kod: {s_no}</div>"
                    html_icerik += f"<img src='data:image/png;base64,{q_b64}'>"
                    if b_b64:
                        html_icerik += f"<img src='data:image/png;base64,{b_b64}'>"
                    html_icerik += "</div>"
                    
                html_icerik += "</div></body></html>"
                st.download_button(label="📄 Toplu Raf Etiketlerini İndir (A4 HTML)", data=html_icerik, file_name="MIDES_Raf_Etiketleri.html", mime="text/html", use_container_width=True)

    with sekme5:
        st.subheader(f"📝 {st.session_state['firma']} Hareket Geçmişi")
        df_gecmis = hareketleri_getir()
        if not df_gecmis.empty:
            st.dataframe(df_gecmis, use_container_width=True, hide_index=True)
            st.download_button(label="📥 Raporu İndir (Excel/CSV)", data=df_gecmis.to_csv(index=False).encode('utf-8-sig'), file_name=f"Hareket_{datetime.now(TR_TZ).strftime('%Y%m%d')}.csv", mime='text/csv')
        else: st.info("Bu firmanın geçmiş bir hareketi bulunmamaktadır.")
            
    with sekme7:
        st.subheader("📑 Piyasa Alımı & Sözleşme Takibi")
        if not df.empty and 'Alım Türü' in df.columns:
            df_piyasa = df[df['Alım Türü'] == 'Piyasa Alımı'].copy()
            if not df_piyasa.empty: st.dataframe(df_piyasa[['Sözleşme No', 'Ürün Adı', 'Miktar', 'Birim', 'Sözleşme Kritik', 'Sözleşme Tarihi', 'Sözleşme Bitiş Tarihi']], use_container_width=True, hide_index=True)
            else: st.info("Kayıtlı sözleşmeli alımınız yoktur.")

    with sekme8:
        st.subheader("💬 Geri Bildirim")
        with st.form("geri_bildirim_formu"):
            tur = st.selectbox("Bildirim Türü", ["Hata Bildirimi", "Soru / Talep"])
            mesaj = st.text_area("Mesajınız:")
            if st.form_submit_button("Gönder") and mesaj.strip():
                supabase.table('geri_bildirimler').insert({
                    "kullanici": st.session_state['kullanici'], "tur": tur,
                    "mesaj": mesaj, "firma": st.session_state.get('firma', 'Bilinmiyor')
                }).execute()
                st.success("İletildi!")
        if st.session_state['rol'] == 'admin':
            st.divider()
            st.subheader("📥 Gelen Tüm Geri Bildirimler")
            try:
                res_gb = supabase.table('geri_bildirimler').select("*").execute()
                if res_gb.data: st.dataframe(tablo_isimleri_degistir(pd.DataFrame(res_gb.data)).sort_values(by="ID", ascending=False), use_container_width=True, hide_index=True)
            except Exception:
                pass

    if st.session_state['rol'] == 'admin':
        with sekme9:
            st.subheader("👥 Kullanıcı Yönetimi")
            
            st.markdown("#### ➕ Yeni Müşteri / Personel Hesabı Aç")
            with st.form("yeni_hesap", clear_on_submit=True):
                c_h1, c_h2, c_h3 = st.columns(3)
                with c_h1:
                    y_kadi = st.text_input("Personel / Kullanıcı Adı")
                    y_sifre = st.text_input("Geçici Şifre", type="password")
                with c_h2: 
                    y_yetki = st.selectbox("Vereceğiniz Yetki", ["Gida", "Temizlik", "Yonetici"])
                with c_h3: 
                    y_firma = st.text_input("Bağlı Olduğu Firma (Örn: X Birliği)")
                
                if st.form_submit_button("Kullanıcı Oluştur"):
                    if y_kadi and y_sifre and y_firma:
                        try:
                            supabase.table('kullanicilar').insert({
                                "kullanici_adi": y_kadi, 
                                "sifre": sifre_hashle(y_sifre),
                                "yetki": y_yetki, 
                                "firma": y_firma, 
                                "ilk_giris": "Evet",
                                "son_guncelleme": datetime.now(TR_TZ).strftime('%Y-%m-%d')
                            }).execute()
                            st.success(f"✅ Tebrikler! '{y_kadi}' adlı kullanıcı başarıyla eklendi.")
                        except Exception as e:
                            st.error("Kayıt sırasında bir hata oluştu. Kullanıcı adı zaten mevcut olabilir.")
                    else: 
                        st.error("Kullanıcı Adı, Şifre dan Firma boş bırakılamaz.")

            st.divider()

            st.markdown("#### 🔄 Mevcut Kullanıcı Şifre Sıfırlama")
            if not df_kullanicilar.empty:
                with st.form("sifre_sifirla_formu", clear_on_submit=True):
                    c_s1, c_s2 = st.columns(2)
                    with c_s1:
                        secilen_kullanici = st.selectbox("Şifresi Sıfırlanacak Kullanıcıyı Seçin", df_kullanicilar['Kullanıcı Adı'].tolist())
                    with c_s2:
                        yeni_gecici_sifre = st.text_input("Yeni Geçici Şifre (Örn: 1234)", type="password")
                        
                    if st.form_submit_button("Şifreyi Sıfırla ve Güvenliğe Zorla"):
                        if yeni_gecici_sifre:
                            hedef_id = int(df_kullanicilar[df_kullanicilar['Kullanıcı Adı'] == secilen_kullanici].iloc[0]['ID'])
                            try:
                                supabase.table('kullanicilar').update({
                                    "sifre": sifre_hashle(yeni_gecici_sifre),
                                    "ilk_giris": "Evet",
                                    "son_guncelleme": datetime.now(TR_TZ).strftime('%Y-%m-%d')
                                }).eq("id", hedef_id).execute()
                                st.success(f"✅ Başarılı! '{secilen_kullanici}' hesabının şifresi sıfırlandı. İlk girişinde kendi şifresini belirlemeye zorlanacak.")
                            except Exception as e:
                                st.error("Sıfırlama sırasında veritabanı hatası oluştu.")
                        else:
                            st.warning("Lütfen yeni geçici şifreyi yazınız.")
            else:
                st.info("Sistemde henüz kayıtlı kullanıcı yok.")

        with sekme10:
            st.subheader("📢 Sistem İçi Duyuru Yayınla")
            mevcut_mesaj = ""
            mevcut_aktif_mi = False
            try:
                res_d = supabase.table('duyurular').select("*").execute()
                if res_d.data:
                    mevcut_mesaj = str(res_d.data[0].get('mesaj', ''))
                    mevcut_aktif_mi = str(res_d.data[0].get('aktif', 'Hayır')) == 'Evet'
            except Exception:
                pass
            
            with st.form("duyuru_formu"):
                d_mesaj = st.text_area("Duyuru Mesajınız:", value=mevcut_mesaj)
                d_aktif = st.checkbox("Duyuruyu Aktif Et (Herkes görsün)", value=mevcut_aktif_mi)
                if st.form_submit_button("Kaydet"):
                    yeni_durum = "Evet" if d_aktif else "Hayır"
                    if not res_d.data:
                        supabase.table('duyurular').insert({"mesaj": d_mesaj, "aktif": yeni_durum}).execute()
                    else:
                        d_id = res_d.data[0]['id']
                        supabase.table('duyurular').update({"mesaj": d_mesaj, "aktif": yeni_durum}).eq("id", d_id).execute()
                    st.success("Duyuru güncellendi!")
                    st.rerun()

    # --- GEMINI YAPAY ZEKA MODÜLÜ (ÇIKIŞ) ---
    with sekme11:
        st.subheader("📂 Akıllı Toplu Çıkış İşlemi")
        giris_yontemi = st.radio("Listeyi Sisteme Nasıl Aktaracaksınız?", ["📸 Fotoğraf Çekerek (Yapay Zeka Okur)", "📥 Excel / CSV Dosyası Yükleyerek"], horizontal=True)
        df_yuklenen = None
        
        if "Fotoğraf" in giris_yontemi:
            st.info("💡 **Gelişmiş Görüntü İşleme:** Listenin fotoğrafını çekin veya yükleyin.")
            resim_dosyasi = st.file_uploader("Kamera ile çekin veya galeriden seçin", type=['jpg', 'jpeg', 'png'])
            
            if resim_dosyasi:
                if st.button("🤖 Yapay Zekaya Okut ve Tablo Oluştur"):
                    with st.spinner("Yapay Zeka tabloyu çözümlüyor, lütfen bekleyin..."):
                        try:
                            gemini_api_key = st.secrets.get("GEMINI_API_KEY", "").strip()
                            if not gemini_api_key:
                                st.error("❌ Gemini API Anahtarı bulunamadı!")
                            else:
                                genai.configure(api_key=gemini_api_key)
                                model = genai.GenerativeModel('gemini-3.5-flash')
                                prompt = """Sen uzman bir veri çıkarma asistanısın. Gönderdiğim fotoğrafta bir 'Malzeme İhtiyaç Listesi' bulunuyor. Tablodaki malzemeleri oku ve her bir satır için sadece 'Stok No' (89 ile başlayan rakamlar) ve düşülecek 'Miktar' (İhtiyaç Miktarı veya Kal. Mktr. sütunu altındaki sayılar) değerlerini çıkar. Miktarı 0 olanları yoksay. Rakamlardaki virgül formatını bozmadan olduğu gibi al. Bana SADECE geçerli bir JSON dizisi döndür, başka hiçbir metin veya markdown işareti ekleme. Örnek Format: [{"Stok No": "8920270048540", "Miktar": "25"}]"""
                                img = Image.open(resim_dosyasi)
                                response = model.generate_content([prompt, img])
                                
                                json_text = response.text.strip()
                                if json_text.startswith("```json"): json_text = json_text.replace("```json", "").replace("```", "").strip()
                                elif json_text.startswith("```"): json_text = json_text.replace("```", "").strip()
                                    
                                ai_data = json.loads(json_text)
                                st.session_state['ai_okunan_df'] = pd.DataFrame(ai_data)
                                st.success("✅ Tablo başarıyla okundu! Aşağıdan onaylayabilirsiniz.")
                        except Exception as e:
                            st.error(f"Sistem Hatası Detayı: {str(e)}")
                
                if 'ai_okunan_df' in st.session_state and st.session_state['ai_okunan_df'] is not None:
                    df_yuklenen = st.session_state['ai_okunan_df']
                    
        else:
            yuklenen_dosya = st.file_uploader("Excel veya CSV Yükleyin", type=['xlsx', 'xls', 'csv'])
            if yuklenen_dosya:
                try: df_yuklenen = pd.read_csv(yuklenen_dosya) if yuklenen_dosya.name.endswith('.csv') else pd.read_excel(yuklenen_dosya)
                except: st.error("Dosya okuma hatası!")

        if df_yuklenen is not None and not df_yuklenen.empty and not df.empty:
            c1, c2, c3 = st.columns(3)
            kolonlar = list(df_yuklenen.columns)
            stok_sutunu = c1.selectbox("Stok No Sütunu:", ["Seçiniz..."] + kolonlar, index=kolonlar.index("Stok No")+1 if "Stok No" in kolonlar else 0)
            miktar_sutunu = c2.selectbox("Miktar Sütunu:", ["Seçiniz..."] + kolonlar, index=kolonlar.index("Miktar")+1 if "Miktar" in kolonlar else 0)
            skt_sutunu = c3.selectbox("SKT Sütunu:", ["Yok (Otomatik)"] + kolonlar)
            
            if stok_sutunu != "Seçiniz..." and miktar_sutunu != "Seçiniz...":
                onay_listesi, hatalar = [], []
                for _, row in df_yuklenen.iterrows():
                    aranan_stok = str(row[stok_sutunu]).strip()
                    if not aranan_stok or aranan_stok == "nan": continue
                    dusulecek = rakam_temizle(row[miktar_sutunu])
                    if dusulecek > 0:
                        eslesen = df[df['Stok No'].astype(str).str.strip() == aranan_stok].copy()
                        if not eslesen.empty:
                            eslesen['SKT_Date'] = pd.to_datetime(eslesen['SKT'], errors='coerce', dayfirst=True)
                            eslesen = eslesen.sort_values(by='SKT_Date')
                            if skt_sutunu != "Yok (Otomatik)":
                                try: a_skt = pd.to_datetime(row[skt_sutunu], dayfirst=True).strftime('%Y-%m-%d')
                                except: a_skt = str(row[skt_sutunu]).strip()
                                tam = eslesen[eslesen['SKT'] == a_skt]
                                if not tam.empty: eslesen = tam
                                else:
                                    hatalar.append(f"❌ {aranan_stok} ürünü için {a_skt} SKT bulunamadı.")
                                    continue
                            mevcut = float(eslesen.iloc[0].get('Miktar', 0) or 0)
                            onay_listesi.append({'Stok No': aranan_stok, 'Ürün Adı': eslesen.iloc[0]['Ürün Adı'], 'İşlem SKT': eslesen.iloc[0]['SKT'], 'Mevcut Stok': mevcut, 'Çıkış Miktarı': dusulecek, 'Kalan Stok': mevcut - dusulecek, 'Durum': "✅ Uygun" if mevcut - dusulecek >= 0 else "⚠️ Yetersiz", 'ID': int(eslesen.iloc[0]['ID'])})
                        else: hatalar.append(f"❌ {aranan_stok} stok no bulunamadı.")
                            
                if onay_listesi:
                    st.markdown("### 🔍 Düzenleme Tablosu")
                    if hatalar:
                        with st.expander("⚠️ Bulunamayanlar"):
                            for h in hatalar: st.write(h)
                    
                    with st.form("toplu_onay_formu"):
                        duzenlenmis_df = st.data_editor(pd.DataFrame(onay_listesi), column_config={"Çıkış Miktarı": st.column_config.NumberColumn("✏️ Çıkış Miktarı", min_value=0.0, step=1.0), "ID": None}, disabled=["Stok No", "Ürün Adı", "İşlem SKT", "Mevcut Stok", "Kalan Stok", "Durum"], hide_index=True, use_container_width=True)
                        
                        c_btn1, c_btn2 = st.columns(2)
                        submit_dus = c_btn1.form_submit_button("💾 Onayla ve Düş")
                        submit_iptal = c_btn2.form_submit_button("❌ Listeyi İptal Et / Temizle")
                        
                        if submit_iptal:
                            st.session_state['ai_okunan_df'] = None
                            st.rerun()

                        if submit_dus:
                            zaman, k_adi, f_adi = datetime.now(TR_TZ).strftime('%Y-%m-%d %H:%M:%S'), st.session_state['kullanici'], st.session_state.get('firma', '')
                            for i, r in duzenlenmis_df.iterrows():
                                g_cik = float(r['Çıkış Miktarı'])
                                if g_cik > 0:
                                    kalan_stok = float(r['Mevcut Stok']) - g_cik
                                    supabase.table(aktif_tablo).update({"miktar": kalan_stok}).eq("id", r['ID']).execute()
                                    log_kaydet(k_adi, "ÇIKIŞ", f"{r['Ürün Adı']} (SKT: {r['İşlem SKT']})", g_cik, "Toplu Çıkış")
                            
                            st.session_state['ai_okunan_df'] = None
                            st.success("✅ Liste başarıyla düşüldü!")
                            st.rerun()
