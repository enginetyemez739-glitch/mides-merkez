import streamlit as st
import pandas as pd
from datetime import datetime
import os
import qrcode
from io import BytesIO
from PIL import Image
import requests
import cv2
import numpy as np
import json
import gspread
from google.oauth2.service_account import Credentials
import hashlib
import base64

st.set_page_config(page_title="MİDES - Akıllı Depo", page_icon="📦", layout="wide")

def sifre_hashle(sifre):
    return hashlib.sha256(str(sifre).encode('utf-8')).hexdigest()

# --- GİZLİ KASA AYARLARI ---
try:
    google_json_str = st.secrets["google_json"]
except:
    st.error("Gizli kasa (Secrets) ayarları bulunamadı!")
    st.stop()

# --- GOOGLE SHEETS BAĞLANTISI ---
scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds_dict = json.loads(google_json_str)
creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

try:
    sheet = client.open('MİDES - Gıda Deposu')
    kullanici_tablosu = client.open("MİDES - Kullanıcılar").get_worksheet(0)
    df_kullanicilar = pd.DataFrame(kullanici_tablosu.get_all_records())
except:
    st.error("Google Drive'da gerekli tablolar bulunamadı. 'MİDES - Kullanıcılar' ve 'MİDES - Gıda Deposu' tablolarını kontrol edin.")
    st.stop()

try:
    ws_malzemeler = sheet.worksheet("Malzemeler")
except:
    ws_malzemeler = sheet.add_worksheet(title="Malzemeler", rows="1000", cols="20")
    ws_malzemeler.append_row(["ID", "Stok No", "Ürün Adı", "Miktar", "Birim", "Eklenme Tarihi", "SKT", "Üretim Tarihi", "Giriş Tarihi", "Resim Yolu", "Kritik Stok"])

try:
    ws_hareket = sheet.worksheet("Hareket_Gecmisi")
except:
    ws_hareket = sheet.add_worksheet(title="Hareket_Gecmisi", rows="1000", cols="10")
    ws_hareket.append_row(["ID", "Tarih", "Kullanıcı", "İşlem", "Ürün Adı", "Miktar", "Açıklama"])

def log_kaydet(kullanici, islem_tipi, urun_adi, miktar, aciklama):
    zaman = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    mevcut_id = len(ws_hareket.get_all_values())
    ws_hareket.append_row([mevcut_id, zaman, kullanici, islem_tipi, urun_adi, miktar, aciklama])

def verileri_getir():
    kayitlar = ws_malzemeler.get_all_records()
    if not kayitlar:
        return pd.DataFrame(columns=["ID", "Stok No", "Ürün Adı", "Miktar", "Birim", "Eklenme Tarihi", "SKT", "Üretim Tarihi", "Giriş Tarihi", "Resim Yolu", "Kritik Stok"])
    return pd.DataFrame(kayitlar)

def hareketleri_getir():
    kayitlar = ws_hareket.get_all_records()
    if not kayitlar:
        return pd.DataFrame(columns=["ID", "Tarih", "Kullanıcı", "İşlem", "Ürün Adı", "Miktar", "Açıklama"])
    return pd.DataFrame(kayitlar).sort_values(by="ID", ascending=False)

def qr_olustur(metin):
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(metin)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def telegram_mesaj_gonder(mesaj):
    if 'telegram_token' in st.session_state and 'telegram_chat_id' in st.session_state:
        token = st.session_state['telegram_token']
        chat_id = st.session_state['telegram_chat_id']
        if token and chat_id and str(token).lower() != "nan" and str(chat_id).lower() != "nan":
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": mesaj}
            try: requests.post(url, data=payload)
            except: pass

# --- YENİ OTURUM VE ŞİFRE YÖNETİMİ ---
if 'giris_yapildi' not in st.session_state:
    st.session_state.update({'giris_yapildi': False, 'kullanici': "", 'rol': "", 'sifre_degistirme_modu': False, 'ilk_giris_uyarisi': False})

if st.session_state['sifre_degistirme_modu']:
    if st.session_state.get('ilk_giris_uyarisi'):
        st.warning("⚠️ Sisteme ilk girişiniz! Lütfen devam etmek için şifrenizi belirleyin.")
    else:
        st.warning("⚠️ Şifrenizin kullanım süresi (90 gün) dolmuş veya değişiklik talep ettiniz. Lütfen yeni şifre belirleyin.")
        
    yeni_sifre = st.text_input("Yeni Şifre:", type="password")
    yeni_sifre_tekrar = st.text_input("Yeni Şifre (Tekrar):", type="password")
    
    if st.button("Şifreyi Güncelle"):
        if yeni_sifre == yeni_sifre_tekrar and len(yeni_sifre) >= 4:
            satir_no = df_kullanicilar[df_kullanicilar['Kullanıcı Adı'] == st.session_state['kullanici']].index[0] + 2
            bugun = datetime.today().strftime('%Y-%m-%d')
            
            yeni_sifre_hash = sifre_hashle(yeni_sifre)
            kullanici_tablosu.update_cell(satir_no, df_kullanicilar.columns.get_loc('Şifre') + 1, yeni_sifre_hash)
            kullanici_tablosu.update_cell(satir_no, df_kullanicilar.columns.get_loc('Son Güncelleme') + 1, bugun)
            
            if 'İlk Giriş' in df_kullanicilar.columns:
                kullanici_tablosu.update_cell(satir_no, df_kullanicilar.columns.get_loc('İlk Giriş') + 1, 'Hayır')
            
            st.success("Şifreniz güncellendi! Lütfen sayfayı yenileyerek yeni şifrenizle giriş yapın.")
            st.session_state['sifre_degistirme_modu'] = False
            st.session_state['giris_yapildi'] = False
            st.session_state['ilk_giris_uyarisi'] = False
            st.stop()
        else:
            st.error("Şifreler uyuşmuyor veya çok kısa (en az 4 karakter olmalı).")
    st.stop()

if not st.session_state['giris_yapildi']:
    c_img1, c_img2, c_img3 = st.columns([2, 1, 2])
    with c_img2:
        try: st.image("amblem.png", use_container_width=True)
        except: pass
        
    st.markdown("<h1 style='text-align: center;'>🔐 MİDES Depo Yönetim Sistemi</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            kadi_input = st.text_input("Kullanıcı Adı")
            sifre_input = st.text_input("Şifre", type="password")
            if st.form_submit_button("Giriş Yap", use_container_width=True):
                girilen_hash = sifre_hashle(sifre_input)
                kullanici = df_kullanicilar[
                    (df_kullanicilar['Kullanıcı Adı'] == kadi_input) & 
                    ((df_kullanicilar['Şifre'].astype(str) == str(sifre_input)) | (df_kullanicilar['Şifre'].astype(str) == girilen_hash))
                ]
                
                if not kullanici.empty:
                    yetki = kullanici['Yetki'].values[0]
                    if yetki == "Gida" or yetki == "Yonetici":
                        st.session_state['kullanici'] = kadi_input
                        st.session_state['rol'] = "admin" if yetki == "Yonetici" else "personel"
                        
                        st.session_state['telegram_token'] = str(kullanici['Telegram Token'].values[0]) if 'Telegram Token' in kullanici else ""
                        st.session_state['telegram_chat_id'] = str(kullanici['Chat ID'].values[0]) if 'Chat ID' in kullanici else ""
                        
                        ilk_giris = str(kullanici['İlk Giriş'].values[0]).strip().lower() if 'İlk Giriş' in kullanici else "hayır"
                        if ilk_giris == "evet":
                            st.session_state['sifre_degistirme_modu'] = True
                            st.session_state['ilk_giris_uyarisi'] = True
                            st.rerun()
                        else:
                            son_guncelleme = pd.to_datetime(kullanici['Son Güncelleme'].values[0], errors='coerce')
                            gecen_gun = (datetime.today() - son_guncelleme).days
                            kalan_gun = 90 - gecen_gun
                            
                            if gecen_gun >= 90:
                                st.session_state['sifre_degistirme_modu'] = True
                            else:
                                st.session_state['sifre_degistirme_modu'] = False
                                st.session_state['giris_yapildi'] = True
                                
                                if kalan_gun <= 5:
                                    st.warning(f"⚠️ Dikkat: Şifrenizin geçerlilik süresinin dolmasına {kalan_gun} gün kalmıştır.")
                                
                                st.rerun()
                    else:
                        st.error("❌ Bu depoya giriş yetkiniz bulunmamaktadır!")
            else:
                st.error("❌ Kullanıcı adı veya şifre hatalı!")
else:
    df = verileri_getir()
    bugun = datetime.now().date()
                        
    c_ust1, c_ust2 = st.columns([4, 1])
    with c_ust1: st.title("📦 MİDES - Merkezi İkmal ve Depo Sistemi")
    with c_ust2:
        st.write(f"👤 {st.session_state['kullanici']}")
        if st.button("🔄 Şifre Değiştir"):
            st.session_state['sifre_degistirme_modu'] = True
            st.rerun()
        if st.button("🚪 Çıkış Yap"):
            st.session_state['giris_yapildi'] = False
            st.rerun()

    sekme1, sekme2, sekme3, sekme6, sekme4, sekme5 = st.tabs(["📊 Özet", "➕ Ürün Ekle", "🔄 Güncelle", "⚡ Hızlı İşlem", "🪪 Ürün Kartı", "📝 Geçmiş"])

    with sekme1:
        st.markdown("### 📋 Depo Uyarıları")
        krt_sayisi = 0
        telegram_raporu = "⚠️ MİDES KRİTİK UYARI RAPORU ⚠️\n\n"
        
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
                
                miktar_val = float(miktar_metni)
                kritik_val = float(kritik_metni)
                
                if miktar_val <= kritik_val:
                    st.error(f"📉 STOK ALARMI: {urun_adi} (Stok No: {stok_no}) bitmek üzere! (Kalan: {int(miktar_val)} {birim})")
                    telegram_raporu += f"📉 ALARM: {urun_adi} (Stok No: {stok_no}) (Kalan: {int(miktar_val)} {birim})\n"
                    krt_sayisi += 1
            except: pass

        if krt_sayisi == 0:
            st.success("✅ Depo durumu çok iyi. Tarihi yaklaşan veya stoğu tükenen ürün yok.")
            telegram_raporu += "✅ Kritik ürün bulunmamaktadır. Depo güvende!"

        if st.button("📲 Telegram'a Rapor Gönder", type="primary"):
            telegram_mesaj_gonder(telegram_raporu)
            st.toast("✅ Gönderildi!")
            
        st.divider()
        st.markdown("### 📦 Stok Numarasına Göre Genel Toplamlar")
        try:
            df['Miktar_Sayi'] = pd.to_numeric(df['Miktar'], errors='coerce').fillna(0)
            toplam_stok_df = df.groupby('Stok No').agg({'Ürün Adı': 'first', 'Miktar_Sayi': 'sum', 'Birim': 'first'}).reset_index()
            toplam_stok_df.rename(columns={'Miktar_Sayi': 'Toplam Miktar'}, inplace=True)
            toplam_stok_df = toplam_stok_df[['Stok No', 'Ürün Adı', 'Toplam Miktar', 'Birim']]
            st.dataframe(toplam_stok_df, use_container_width=True, hide_index=True)
        except: st.info("Toplamlar hesaplanırken hata oluştu.")

        st.markdown("### 🔍 Detaylı Parti Listesi")
        gosterilecek_df = df.drop(columns=['Resim Yolu', 'Miktar_Sayi'], errors='ignore')
        st.dataframe(gosterilecek_df, use_container_width=True, hide_index=True)

    with sekme2:
        st.subheader("Depoya Yeni Ürün Ekle")
        with st.form("urun_ekle_formu"):
            col1, col2 = st.columns(2)
        
        with col1:
            stok_no = st.text_input("Stok Numarası (Barkod)")
            urun_adi = st.text_input("Ürün Adı")
            miktar = st.number_input("Miktar", min_value=0.0, step=1.0)
            birim = st.selectbox("Birim", ["Kg", "Litre", "Adet", "Kutu", "Paket"])
            
        with col2:
            kritik_seviye = st.number_input("Kritik Uyarı Seviyesi", min_value=1, value=20)
            uretim_tarihi = st.date_input("Üretim Tarihi")
            skt = st.date_input("Son Kullanma Tarihi (SKT)")
            ekle_btn = st.form_submit_button("Ürünü Kaydet", use_container_width=True)
        
        if ekle_btn:
            if urun_adi and stok_no:
                bugun_tarih = datetime.now().strftime("%Y-%m-%d")
                yeni_id = 1 if df.empty else int(df['ID'].max()) + 1
                yeni_satir = [yeni_id, stok_no, urun_adi, miktar, birim, bugun_tarih, str(skt), str(uretim_tarihi), bugun_tarih, "", kritik_seviye]
                ws_malzemeler.append_row(yeni_satir)
                log_kaydet(st.session_state['kullanici'], "YENİ KAYIT", urun_adi, miktar, "Sisteme ilk kez eklendi")
                st.success(f"✅ {urun_adi} depoya başarıyla kaydedildi! Sayfa yenileniyor...")
                st.rerun()
            else:
                st.error("Lütfen Stok Numarası ve Ürün Adı alanlarını doldurunuz.")

    with sekme3:
        st.subheader("🔄 Ürün Bilgilerini Güncelle")
        if not df.empty:
            secili_guncelleme = st.selectbox("Ürünü seçin:", df['ID'].astype(str) + " - " + df['Ürün Adı'])
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
                    try: 
                        skt_val = datetime.strptime(str(urun.get('SKT', '')).strip(), '%Y-%m-%d').date()
                    except: 
                        skt_val = bugun
                    y_skt = st.date_input("SKT:", value=skt_val)
                    y_kritik = st.number_input("Kritik Sınır:", value=int(float(str(urun.get('Kritik Stok', '10')).strip() or '10')), step=1)
                
                if st.form_submit_button("💾 Kaydet", type="primary"):
                    satir = df[df['ID'] == secili_id].index[0] + 2
                    ws_malzemeler.update_cell(satir, 2, yeni_stok) 
                    ws_malzemeler.update_cell(satir, 4, urun_miktar - cikis + giris)  
                    ws_malzemeler.update_cell(satir, 7, y_skt.strftime('%Y-%m-%d')) 
                    ws_malzemeler.update_cell(satir, 11, y_kritik) 
                    
                    if cikis > 0: log_kaydet(st.session_state['kullanici'], "ÇIKIŞ", urun['Ürün Adı'], cikis, "Manuel Güncelleme")
                    if giris > 0: log_kaydet(st.session_state['kullanici'], "GİRİŞ", urun['Ürün Adı'], giris, "Manuel Güncelleme")
                    st.success("Güncellendi!")
                    st.rerun()
