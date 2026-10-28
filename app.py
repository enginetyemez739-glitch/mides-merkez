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

# --- GOOGLE SHEETS BAĞLANTISI (ÖNBELLEKLİ - HIZ LİMİTİ KORUMASI) ---
@st.cache_resource(ttl=600)
def google_baglantisini_kur():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds_dict = json.loads(google_json_str)
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    
    sheet = client.open('MİDES - Gıda Deposu')
    kullanici_tablosu = client.open("MİDES - Kullanıcılar").get_worksheet(0)
    
    mevcut_sekmeler = {ws.title: ws for ws in sheet.worksheets()}
    
    def get_or_create_ws(baslik, cols="20"):
        if baslik in mevcut_sekmeler:
            return mevcut_sekmeler[baslik]
        else:
            return sheet.add_worksheet(title=baslik, rows="1000", cols=cols)

    w_gida = get_or_create_ws("gida_deposu")
    w_temizlik = get_or_create_ws("temizlik_deposu")
    w_hareket = get_or_create_ws("Hareket_Gecmisi", cols="10")
    w_geri = get_or_create_ws("Geri_Bildirimler", cols="10")
    
    # Başlıkları sadece eksikse ekle
    if not w_gida.row_values(1): w_gida.append_row(["ID", "Stok No", "Ürün Adı", "Miktar", "Birim", "Eklenme Tarihi", "SKT", "Üretim Tarihi", "Giriş Tarihi", "Resim Yolu", "Kritik Stok", "Alım Türü", "Sözleşme No", "Sözleşme Tarihi", "Sözleşme Bitiş Tarihi", "Sözleşme Kritik", "Firma"])
    if not w_temizlik.row_values(1): w_temizlik.append_row(["ID", "Stok No", "Ürün Adı", "Miktar", "Birim", "Eklenme Tarihi", "SKT", "Üretim Tarihi", "Giriş Tarihi", "Resim Yolu", "Kritik Stok", "Alım Türü", "Sözleşme No", "Sözleşme Tarihi", "Sözleşme Bitiş Tarihi", "Sözleşme Kritik", "Firma"])
    if not w_hareket.row_values(1): w_hareket.append_row(["ID", "Tarih", "Kullanıcı", "İşlem", "Ürün Adı", "Miktar", "Açıklama", "Firma"])
    if not w_geri.row_values(1): w_geri.append_row(["ID", "Tarih", "Kullanıcı", "Tür", "Mesaj", "Firma"])
    
    return client, sheet, kullanici_tablosu, w_gida, w_temizlik, w_hareket, w_geri

try:
    client, sheet, kullanici_tablosu, ws_gida, ws_temizlik, ws_hareket, ws_geri_bildirim = google_baglantisini_kur()
    df_kullanicilar = pd.DataFrame(kullanici_tablosu.get_all_records())
except Exception as e:
    st.error("Google sistemi anlık olarak çok fazla istek aldı. Lütfen 1 dakika bekleyip sayfayı yenileyin.")
    st.stop()

def log_kaydet(kullanici, islem_tipi, urun_adi, miktar, aciklama):
    zaman = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    mevcut_id = len(ws_hareket.get_all_values())
    firma_adi = st.session_state.get('firma', 'Bilinmiyor')
    satir = [mevcut_id, zaman, kullanici, islem_tipi, urun_adi, miktar, aciklama, firma_adi]
    
    headers = ws_hareket.row_values(1)
    if "Firma" not in headers: ws_hareket.update_cell(1, 8, "Firma")
    
    ws_hareket.append_row(satir)

def verileri_getir(ws):
    kayitlar = ws.get_all_records()
    df = pd.DataFrame(kayitlar)
    if not df.empty:
        df['GS_Row'] = df.index + 2
        filtre_sutunu = 'Firma' if 'Firma' in df.columns else 'Depo Sahibi' if 'Depo Sahibi' in df.columns else None
        
        if filtre_sutunu and st.session_state['rol'] != 'admin':
            df = df[df[filtre_sutunu].astype(str) == st.session_state['firma']]
    else:
        df = pd.DataFrame(columns=["ID", "Stok No", "Ürün Adı", "Miktar", "Birim", "Eklenme Tarihi", "SKT", "Üretim Tarihi", "Giriş Tarihi", "Resim Yolu", "Kritik Stok", "Alım Türü", "Sözleşme No", "Sözleşme Tarihi", "Sözleşme Bitiş Tarihi", "Sözleşme Kritik", "Firma", "GS_Row"])
    return df

def hareketleri_getir():
    kayitlar = ws_hareket.get_all_records()
    df = pd.DataFrame(kayitlar)
    if not df.empty:
        if st.session_state['rol'] != 'admin':
            if 'Firma' in df.columns:
                df = df[df['Firma'].astype(str) == st.session_state['firma']]
            else:
                df = df[df['Kullanıcı'].astype(str) == st.session_state['kullanici']]
        return df.sort_values(by="ID", ascending=False)
    return pd.DataFrame(columns=["ID", "Tarih", "Kullanıcı", "İşlem", "Ürün Adı", "Miktar", "Açıklama", "Firma"])

def geri_bildirimleri_getir():
    kayitlar = ws_geri_bildirim.get_all_records()
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
    st.session_state.update({'giris_yapildi': False, 'kullanici': "", 'rol': "", 'firma': "", 'sifre_degistirme_modu': False, 'ilk_giris_uyarisi': False})

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
                    yetki = str(kullanici['Yetki'].values[0]).strip().lower()
                    if yetki in ["gida", "gıda", "temizlik", "yonetici", "yönetici"]:
                        st.session_state['kullanici'] = kadi_input
                        
                        firma = str(kullanici['Firma'].values[0]).strip() if 'Firma' in kullanici else kadi_input
                        st.session_state['firma'] = firma if firma and firma.lower() != "nan" else kadi_input
                        
                        if yetki in ["yonetici", "yönetici"]:
                            st.session_state['rol'] = "admin"
                        elif yetki in ["gida", "gıda"]:
                            st.session_state['rol'] = "gida"
                        else:
                            st.session_state['rol'] = "temizlik"
                        
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
                            if gecen_gun >= 90:
                                st.session_state['sifre_degistirme_modu'] = True
                            else:
                                st.session_state['sifre_degistirme_modu'] = False
                                st.session_state['giris_yapildi'] = True
                                st.rerun()
                    else:
                        st.error("❌ Bu sisteme giriş yetkiniz bulunmamaktadır!")
            else:
                st.error("❌ Kullanıcı adı veya şifre hatalı!")
else:
    # --- YÖNETİCİ DEPO SEÇİMİ ---
    if st.session_state['rol'] == 'admin':
        st.info("👑 **Yönetici Modu:** Kendi firma/birim alanınızda işlemlerinizi yürütebilirsiniz.")
        secilen_depo = st.selectbox("Aktif Depo", ["🍎 Gıda Deposu", "🧹 Temizlik Deposu"])
        aktif_ws = ws_gida if "Gıda" in secilen_depo else ws_temizlik
        depo_adi = "Gıda Deposu" if "Gıda" in secilen_depo else "Temizlik Deposu"
    else:
        if st.session_state['rol'] == 'gida':
            aktif_ws = ws_gida
            depo_adi = "Gıda Deposu"
        else:
            aktif_ws = ws_temizlik
            depo_adi = "Temizlik Deposu"

    df = verileri_getir(aktif_ws)
    bugun = datetime.now().date()
                        
    c_ust1, c_ust2 = st.columns([4, 1])
    with c_ust1: st.title(f"📦 {st.session_state['firma']} - {depo_adi}")
    with c_ust2:
        st.write(f"👤 {st.session_state['kullanici']} ({'Yönetici' if st.session_state['rol'] == 'admin' else 'Yetkili'})")
        if st.button("🔄 Şifre Değiştir"):
            st.session_state['sifre_degistirme_modu'] = True
            st.rerun()
        if st.button("🚪 Çıkış Yap"):
            st.session_state['giris_yapildi'] = False
            st.rerun()

    if st.session_state['rol'] == 'admin':
        sekme1, sekme2, sekme3, sekme6, sekme4, sekme5, sekme7, sekme8, sekme9 = st.tabs(["📊 Özet", "➕ Ürün Ekle", "🔄 Güncelle", "⚡ Hızlı İşlem", "🪪 Ürün Kartı", "📝 Geçmiş İşlemler", "📑 Sözleşmeler", "💬 Bildirimler", "👥 Kullanıcı Yönetimi"])
    else:
        sekme1, sekme2, sekme3, sekme6, sekme4, sekme5, sekme7, sekme8 = st.tabs(["📊 Özet", "➕ Ürün Ekle", "🔄 Güncelle", "⚡ Hızlı İşlem", "🪪 Ürün Kartı", "📝 Depo Geçmişi", "📑 Sözleşmeler", "💬 Geri Bildirim"])

    with sekme1:
        st.markdown(f"### 📋 Uyarılar")
        krt_sayisi = 0
        telegram_raporu = f"⚠️ {st.session_state['firma']} - {depo_adi.upper()} UYARI RAPORU ⚠️\n\n"
        
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
                    st.error(f"📉 STOK ALARMI: {urun_adi} bitmek üzere! (Kalan: {int(miktar_val)} {birim})")
                    telegram_raporu += f"📉 ALARM: {urun_adi} (Kalan: {int(miktar_val)} {birim})\n"
                    krt_sayisi += 1
            except: pass

        if krt_sayisi == 0:
            st.success("✅ Depo durumu çok iyi. Tarihi yaklaşan veya stoğu tükenen ürün yok.")

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
        gosterilecek_df = df.drop(columns=['Resim Yolu', 'Miktar_Sayi', 'GS_Row', 'Depo Sahibi', 'Firma'], errors='ignore')
        st.dataframe(gosterilecek_df, use_container_width=True, hide_index=True)

    with sekme2:
        st.subheader("Depoya Yeni Ürün Ekle")
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
            
            ekle_btn = st.form_submit_button("Ürünü Kaydet", use_container_width=True)
        
        if ekle_btn:
            if urun_adi and stok_no:
                bugun_tarih = datetime.now().strftime("%Y-%m-%d")
                y_id = 1 if aktif_ws.get_all_records() == [] else len(aktif_ws.get_all_records()) + 1
                
                s_no = sozlesme_no if alim_turu == "Piyasa Alımı" else "-"
                s_tar = str(sozlesme_tarihi) if alim_turu == "Piyasa Alımı" else "-"
                s_bit = str(sozlesme_bitis) if alim_turu == "Piyasa Alımı" else "-"
                s_krt = sozlesme_kritik if alim_turu == "Piyasa Alımı" else 0.0
                
                sahip_firma = st.session_state['firma']

                yeni_satir = [y_id, stok_no, urun_adi, miktar, birim, bugun_tarih, str(skt), str(uretim_tarihi), bugun_tarih, "", kritik_seviye, alim_turu, s_no, s_tar, s_bit, s_krt, sahip_firma]
                
                satir_tam = yeni_satir + [""] * max(0, len(aktif_ws.row_values(1)) - len(yeni_satir))
                aktif_ws.append_row(satir_tam[:len(aktif_ws.row_values(1))])
                
                log_kaydet(st.session_state['kullanici'], "YENİ KAYIT", urun_adi, miktar, f"{alim_turu} ile eklendi")
                st.success(f"✅ Ürün {sahip_firma} deposuna başarıyla kaydedildi!")
                # Önbelleği temizle ki yeni veri anında görünsün
                st.cache_resource.clear()
                st.rerun()
            else:
                st.error("Lütfen Stok Numarası ve Ürün Adı alanlarını doldurunuz.")

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
                kaydet_tik = c_btn1.form_submit_button("💾 Güncellemeyi Kaydet", type="primary")
                sil_tik = c_btn2.form_submit_button("🗑️ Ürünü Depodan Tamamen Sil")
                
                if kaydet_tik:
                    satir = int(urun['GS_Row'])
                    aktif_ws.update_cell(satir, 2, yeni_stok) 
                    aktif_ws.update_cell(satir, 4, urun_miktar - cikis + giris)  
                    aktif_ws.update_cell(satir, 7, y_skt.strftime('%Y-%m-%d')) 
                    aktif_ws.update_cell(satir, 11, y_kritik) 
                    
                    if cikis > 0: log_kaydet(st.session_state['kullanici'], "ÇIKIŞ", urun['Ürün Adı'], cikis, "Manuel Güncelleme")
                    if giris > 0: log_kaydet(st.session_state['kullanici'], "GİRİŞ", urun['Ürün Adı'], giris, "Manuel Güncelleme")
                    st.success("Güncellendi!")
                    st.cache_resource.clear()
                    st.rerun()
                    
                if sil_tik:
                    satir = int(urun['GS_Row'])
                    aktif_ws.delete_rows(satir)
                    log_kaydet(st.session_state['kullanici'], "SİLME", urun['Ürün Adı'], urun_miktar, "Ürün depodan tamamen kaldırıldı")
                    st.success(f"🗑️ Ürün depodan silindi!")
                    st.cache_resource.clear()
                    st.rerun()

    with sekme6:
        st.subheader("⚡ Hızlı İşlem (Barkod ile)")
        aranan_stok = st.text_input("🔍 Stok Numarasını Yazın:")
        resim = st.camera_input("📷 Veya QR Okut")
        bulunan = str(aranan_stok).strip() if aranan_stok else None
        
        if resim:
            cv_img = cv2.cvtColor(np.array(Image.open(resim)), cv2.COLOR_RGB2BGR)
            data, _, _ = cv2.QRCodeDetector().detectAndDecode(cv_img)
            if data:
                try: bulunan = next((s.split("Stok No:")[1].strip() for s in data.split('\n') if "Stok No:" in s), None)
                except: pass
                
        if bulunan:
            eslesen = df[df['Stok No'].astype(str).str.strip() == bulunan]
            if not eslesen.empty:
                st.info(f"📦 Bulunan Ürün: {eslesen.iloc[0]['Ürün Adı']} (Mevcut: {eslesen.iloc[0]['Miktar']})")
                with st.form("hizli"):
                    m_dus = st.number_input("➖ Çıkar:", min_value=0, step=1)
                    m_ekle = st.number_input("➕ Ekle:", min_value=0, step=1)
                    if st.form_submit_button("💾 Güncelle", type="primary"):
                        if m_dus > 0 or m_ekle > 0:
                            satir = int(eslesen.iloc[0]['GS_Row'])
                            aktif_ws.update_cell(satir, 4, int(eslesen.iloc[0]['Miktar']) - m_dus + m_ekle)
                            if m_dus > 0: log_kaydet(st.session_state['kullanici'], "ÇIKIŞ", eslesen.iloc[0]['Ürün Adı'], m_dus, "Hızlı İşlem")
                            if m_ekle > 0: log_kaydet(st.session_state['kullanici'], "GİRİŞ", eslesen.iloc[0]['Ürün Adı'], m_ekle, "Hızlı İşlem")
                            st.success("Stok güncellendi!")
                            st.cache_resource.clear()
                            st.rerun()
            else: st.error("❌ Ürün deponuzda bulunamadı.")

    with sekme4:
        st.subheader("🪪 Ürün Tanıtım Kartı ve Toplu Çıktı")
        if not df.empty:
            c_kart1, c_kart2 = st.columns(2)
            with c_kart1:
                st.markdown("**Tekli QR Kod**")
                secilen = st.selectbox("Kartı Göster:", df['ID'].astype(str) + " - " + df['Ürün Adı'])
                ub = df[df['ID'] == int(secilen.split(" - ")[0])].iloc[0]
                st.image(qr_olustur(f"Ürün: {ub['Ürün Adı']}\nStok No: {ub['Stok No']}\nMiktar: {ub['Miktar']}\nSKT: {ub['SKT']}"), caption="QR Kod")
            
            with c_kart2:
                st.markdown("**Toplu QR Kod Çıktısı (A4)**")
                st.info("Kendi deponuzdaki ürün barkodlarını A4 formatında yazdırmak için belgeyi indirin.")
                
                html_icerik = "<html><head><meta charset='utf-8'><style>body { font-family: Arial, sans-serif; } .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; } .card { border: 1px dashed #555; padding: 10px; text-align: center; border-radius: 5px; } .card img { width: 110px; height: 110px; margin-top: 5px; } .title { font-size: 14px; font-weight: bold; margin-bottom: 3px; } .stok { font-size: 12px; color: #333; } @media print { .grid { gap: 10px; } .card { page-break-inside: avoid; } }</style></head><body><h2 style='text-align:center;'>MİDES Depo Barkodları</h2><div class='grid'>"
                for _, row in df.iterrows():
                    u_adi = str(row.get('Ürün Adı', ''))
                    s_no = str(row.get('Stok No', ''))
                    q_data = qr_olustur(f"Ürün: {u_adi}\nStok No: {s_no}")
                    b64_qr = base64.b64encode(q_data).decode()
                    html_icerik += f"<div class='card'><div class='title'>{u_adi}</div><div class='stok'>Stok No: {s_no}</div><img src='data:image/png;base64,{b64_qr}'></div>"
                html_icerik += "</div></body></html>"
                
                st.download_button(label="📄 Yazdırılabilir Belgeyi İndir", data=html_icerik, file_name="MIDES_Barkodlar.html", mime="text/html", use_container_width=True)
        else:
            st.info("Deponuzda henüz ürün bulunmuyor.")

    with sekme5:
        st.subheader(f"📝 {st.session_state['firma']} Hareket Geçmişi")
        df_gecmis = hareketleri_getir()
        if not df_gecmis.empty:
            st.dataframe(df_gecmis, use_container_width=True, hide_index=True)
            csv = df_gecmis.to_csv(index=False).encode('utf-8-sig')
            st.download_button(label="📥 Raporu İndir (Excel/CSV)", data=csv, file_name=f"Hareket_Raporu_{datetime.now().strftime('%Y%m%d')}.csv", mime='text/csv')
        else:
            st.info("Bu firmanın geçmiş bir hareketi bulunmamaktadır.")
            
    with sekme7:
        st.subheader("📑 Piyasa Alımı & Sözleşme Takibi")
        if 'Alım Türü' in df.columns:
            df_piyasa = df[df['Alım Türü'] == 'Piyasa Alımı'].copy()
            if not df_piyasa.empty:
                sozlesme_ozet = df_piyasa[['Sözleşme No', 'Ürün Adı', 'Miktar', 'Birim', 'Sözleşme Kritik', 'Sözleşme Tarihi', 'Sözleşme Bitiş Tarihi']]
                st.dataframe(sozlesme_ozet, use_container_width=True, hide_index=True)
            else:
                st.info("Kayıtlı sözleşmeli alımınız yoktur.")

    with sekme8:
        st.subheader("💬 Geri Bildirim")
        with st.form("geri_bildirim_formu"):
            tur = st.selectbox("Bildirim Türü", ["Hata Bildirimi", "Soru / Talep"])
            mesaj = st.text_area("Mesajınız:")
            if st.form_submit_button("Gönder", use_container_width=True) and mesaj.strip():
                zaman = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                firma = st.session_state.get('firma', 'Bilinmiyor')
                satir = [len(ws_geri_bildirim.get_all_values()), zaman, st.session_state['kullanici'], tur, mesaj, firma]
                headers = ws_geri_bildirim.row_values(1)
                if "Firma" not in headers: ws_geri_bildirim.update_cell(1, 6, "Firma")
                ws_geri_bildirim.append_row(satir)
                st.success("İletildi!")

        if st.session_state['rol'] == 'admin':
            st.divider()
            st.subheader("📥 Gelen Tüm Geri Bildirimler (Sadece Size Özel)")
            df_gb = geri_bildirimleri_getir()
            if not df_gb.empty:
                st.dataframe(df_gb, use_container_width=True, hide_index=True)
            else:
                st.info("Henüz kimse geri bildirim göndermemiş.")

    if st.session_state['rol'] == 'admin':
        with sekme9:
            st.subheader("👥 Yeni Müşteri / Personel Hesabı Aç")
            st.info("Buradan yeni kullanıcılara sıfırdan hesap açabilir veya onları var olan bir firmaya/bölüme dahil edebilirsiniz.")
            
            with st.form("yeni_hesap"):
                c_h1, c_h2, c_h3 = st.columns(3)
                with c_h1:
                    y_kadi = st.text_input("Personel / Kullanıcı Adı")
                    y_sifre = st.text_input("Geçici Şifre", type="password")
                with c_h2:
                    y_yetki = st.selectbox("Vereceğiniz Yetki", ["Gida", "Temizlik", "Yonetici"])
                with c_h3:
                    y_firma = st.text_input("Bağlı Olduğu Firma (Örn: X Birliği)")
                
                if st.form_submit_button("Yeni Kullanıcı Hesabı Oluştur", type="primary"):
                    if y_kadi and y_sifre and y_firma:
                        k_headers = kullanici_tablosu.row_values(1)
                        if "Firma" not in k_headers:
                            k_headers.append("Firma")
                            kullanici_tablosu.update_cell(1, len(k_headers), "Firma")
                            
                        yeni_h_satir = [""] * len(k_headers)
                        
                        if "Kullanıcı Adı" in k_headers: yeni_h_satir[k_headers.index("Kullanıcı Adı")] = y_kadi
                        if "Şifre" in k_headers: yeni_h_satir[k_headers.index("Şifre")] = sifre_hashle(y_sifre)
                        if "Yetki" in k_headers: yeni_h_satir[k_headers.index("Yetki")] = y_yetki
                        if "Firma" in k_headers: yeni_h_satir[k_headers.index("Firma")] = y_firma
                        if "İlk Giriş" in k_headers: yeni_h_satir[k_headers.index("İlk Giriş")] = "Evet"
                        if "Son Güncelleme" in k_headers: yeni_h_satir[k_headers.index("Son Güncelleme")] = datetime.now().strftime('%Y-%m-%d')
                        
                        kullanici_tablosu.append_row(yeni_h_satir)
                        st.success(f"Tebrikler! '{y_kadi}' kullanıcısı '{y_firma}' firmasına '{y_yetki}' yetkisiyle başarıyla eklendi.")
                        st.cache_resource.clear()
                        st.rerun()
                    else:
                        st.error("Kullanıcı Adı, Şifre ve Bağlı Olduğu Firma alanları boş bırakılamaz.")
