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
import google.generativeai as genai

st.set_page_config(page_title="MİDES - Akıllı Depo", page_icon="📦", layout="wide")

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

try:
    google_json_str = st.secrets["google_json"]
except:
    st.error("Gizli kasa (Secrets) ayarları bulunamadı!")
    st.stop()

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
        if baslik in mevcut_sekmeler: return mevcut_sekmeler[baslik]
        else: return sheet.add_worksheet(title=baslik, rows="1000", cols=cols)

    w_gida = get_or_create_ws("gida_deposu")
    w_temizlik = get_or_create_ws("temizlik_deposu")
    w_hareket = get_or_create_ws("Hareket_Gecmisi", cols="10")
    w_geri = get_or_create_ws("Geri_Bildirimler", cols="10")
    w_duyuru = get_or_create_ws("Duyurular", cols="2") 
    
    if not w_gida.row_values(1): w_gida.append_row(["ID", "Stok No", "Ürün Adı", "Miktar", "Birim", "Eklenme Tarihi", "SKT", "Üretim Tarihi", "Giriş Tarihi", "Resim Yolu", "Kritik Stok", "Alım Türü", "Sözleşme No", "Sözleşme Tarihi", "Sözleşme Bitiş Tarihi", "Sözleşme Kritik", "Firma"])
    if not w_temizlik.row_values(1): w_temizlik.append_row(["ID", "Stok No", "Ürün Adı", "Miktar", "Birim", "Eklenme Tarihi", "SKT", "Üretim Tarihi", "Giriş Tarihi", "Resim Yolu", "Kritik Stok", "Alım Türü", "Sözleşme No", "Sözleşme Tarihi", "Sözleşme Bitiş Tarihi", "Sözleşme Kritik", "Firma"])
    if not w_hareket.row_values(1): w_hareket.append_row(["ID", "Tarih", "Kullanıcı", "İşlem", "Ürün Adı", "Miktar", "Açıklama", "Firma"])
    if not w_geri.row_values(1): w_geri.append_row(["ID", "Tarih", "Kullanıcı", "Tür", "Mesaj", "Firma"])
    if not w_duyuru.row_values(1): w_duyuru.append_row(["Mesaj", "Aktif"])
    return client, sheet, kullanici_tablosu, w_gida, w_temizlik, w_hareket, w_geri, w_duyuru

try:
    client, sheet, kullanici_tablosu, ws_gida, ws_temizlik, ws_hareket, ws_geri_bildirim, ws_duyuru = google_baglantisini_kur()
    df_kullanicilar = pd.DataFrame(kullanici_tablosu.get_all_records())
except Exception as e:
    st.error("Google sistemi meşgul. Lütfen sayfayı yenileyin.")
    st.stop()

def log_kaydet(kullanici, islem_tipi, urun_adi, miktar, aciklama):
    zaman = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    satir = [len(ws_hareket.get_all_values()), zaman, kullanici, islem_tipi, urun_adi, miktar, aciklama, st.session_state.get('firma', 'Bilinmiyor')]
    headers = ws_hareket.row_values(1)
    if "Firma" not in headers: ws_hareket.update_cell(1, 8, "Firma")
    ws_hareket.append_row(satir)

def verileri_getir(ws):
    df = pd.DataFrame(ws.get_all_records())
    if not df.empty:
        df['GS_Row'] = df.index + 2
        filtre_sutunu = 'Firma' if 'Firma' in df.columns else 'Depo Sahibi' if 'Depo Sahibi' in df.columns else None
        if filtre_sutunu and st.session_state['rol'] != 'admin': df = df[df[filtre_sutunu].astype(str) == st.session_state['firma']]
    else: df = pd.DataFrame(columns=["ID", "Stok No", "Ürün Adı", "Miktar", "Birim", "Eklenme Tarihi", "SKT", "Üretim Tarihi", "Giriş Tarihi", "Resim Yolu", "Kritik Stok", "Alım Türü", "Sözleşme No", "Sözleşme Tarihi", "Sözleşme Bitiş Tarihi", "Sözleşme Kritik", "Firma", "GS_Row"])
    return df

def hareketleri_getir():
    df = pd.DataFrame(ws_hareket.get_all_records())
    if not df.empty:
        if st.session_state['rol'] != 'admin':
            if 'Firma' in df.columns: df = df[df['Firma'].astype(str) == st.session_state['firma']]
            else: df = df[df['Kullanıcı'].astype(str) == st.session_state['kullanici']]
        return df.sort_values(by="ID", ascending=False)
    return pd.DataFrame(columns=["ID", "Tarih", "Kullanıcı", "İşlem", "Ürün Adı", "Miktar", "Açıklama", "Firma"])

def geri_bildirimleri_getir(): return pd.DataFrame(ws_geri_bildirim.get_all_records()).sort_values(by="ID", ascending=False)

def qr_olustur(metin):
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(metin)
    qr.make(fit=True)
    buf = BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
    return buf.getvalue()

def telegram_mesaj_gonder(mesaj):
    token = st.session_state.get('telegram_token', '')
    chat_id = st.session_state.get('telegram_chat_id', '')
    if token and chat_id and str(token).lower() != "nan" and str(chat_id).lower() != "nan":
        try: requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": mesaj})
        except: pass

if 'giris_yapildi' not in st.session_state:
    st.session_state.update({'giris_yapildi': False, 'kullanici': "", 'rol': "", 'firma': "", 'sifre_degistirme_modu': False, 'ilk_giris_uyarisi': False})

if st.session_state['sifre_degistirme_modu']:
    st.warning("⚠️ Şifre belirleme/değiştirme ekranındasınız.")
    y_sifre, y_sifre_tekrar = st.text_input("Yeni Şifre:", type="password"), st.text_input("Yeni Şifre (Tekrar):", type="password")
    if st.button("Şifreyi Güncelle"):
        if y_sifre == y_sifre_tekrar and len(y_sifre) >= 4:
            satir_no = df_kullanicilar[df_kullanicilar['Kullanıcı Adı'] == st.session_state['kullanici']].index[0] + 2
            kullanici_tablosu.update_cell(satir_no, df_kullanicilar.columns.get_loc('Şifre') + 1, sifre_hashle(y_sifre))
            kullanici_tablosu.update_cell(satir_no, df_kullanicilar.columns.get_loc('Son Güncelleme') + 1, datetime.today().strftime('%Y-%m-%d'))
            if 'İlk Giriş' in df_kullanicilar.columns: kullanici_tablosu.update_cell(satir_no, df_kullanicilar.columns.get_loc('İlk Giriş') + 1, 'Hayır')
            st.success("Şifreniz güncellendi! Yeniden giriş yapın.")
            st.session_state.update({'sifre_degistirme_modu': False, 'giris_yapildi': False, 'ilk_giris_uyarisi': False})
            st.stop()
        else: st.error("Şifreler uyuşmuyor veya çok kısa.")
    st.stop()

if not st.session_state['giris_yapildi']:
    c_img1, c_img2, c_img3 = st.columns([2, 1, 2])
    with c_img2:
        try: st.image("amblem.png", use_container_width=True)
        except: pass
    st.markdown("<h1 style='text-align: center;'>🔐 MİDES Depo Yönetim Sistemi</h1>", unsafe_allow_html=True)
    _, col2, _ = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            kadi_input, sifre_input = st.text_input("Kullanıcı Adı"), st.text_input("Şifre", type="password")
            if st.form_submit_button("Giriş Yap", use_container_width=True):
                kullanici = df_kullanicilar[(df_kullanicilar['Kullanıcı Adı'] == kadi_input) & ((df_kullanicilar['Şifre'].astype(str) == str(sifre_input)) | (df_kullanicilar['Şifre'].astype(str) == sifre_hashle(sifre_input)))]
                if not kullanici.empty:
                    yetki = str(kullanici['Yetki'].values[0]).strip().lower()
                    if yetki in ["gida", "gıda", "temizlik", "yonetici", "yönetici", "merkez yönetici"]:
                        st.session_state['kullanici'] = kadi_input
                        firma = str(kullanici['Firma'].values[0]).strip() if 'Firma' in kullanici else kadi_input
                        st.session_state['firma'] = firma if firma and firma.lower() != "nan" else kadi_input
                        st.session_state['rol'] = "admin" if yetki in ["yonetici", "yönetici", "merkez yönetici"] else "gida" if yetki in ["gida", "gıda"] else "temizlik"
                        st.session_state['telegram_token'] = str(kullanici['Telegram Token'].values[0]) if 'Telegram Token' in kullanici else ""
                        st.session_state['telegram_chat_id'] = str(kullanici['Chat ID'].values[0]) if 'Chat ID' in kullanici else ""
                        if str(kullanici.get('İlk Giriş', ['hayır']).values[0]).strip().lower() == "evet":
                            st.session_state.update({'sifre_degistirme_modu': True, 'ilk_giris_uyarisi': True})
                            st.rerun()
                        elif (datetime.today() - pd.to_datetime(kullanici['Son Güncelleme'].values[0], errors='coerce')).days >= 90:
                            st.session_state['sifre_degistirme_modu'] = True
                            st.rerun()
                        else:
                            st.session_state['giris_yapildi'] = True
                            st.rerun()
                    else: st.error("❌ Yetkiniz bulunmamaktadır!")
                else: st.error("❌ Kullanıcı adı veya şifre hatalı!")
else:
    if st.session_state['rol'] == 'admin':
        st.info("👑 **Merkezi Yönetici Modu:** Kendi firmanız adına işlemlerinizi yürütebilirsiniz.")
        secilen_depo = st.selectbox("Aktif Depo", ["🍎 Gıda Deposu", "🧹 Temizlik Deposu"])
        aktif_ws = ws_gida if "Gıda" in secilen_depo else ws_temizlik
        depo_adi = "Gıda Deposu" if "Gıda" in secilen_depo else "Temizlik Deposu"
    else:
        aktif_ws = ws_gida if st.session_state['rol'] == 'gida' else ws_temizlik
        depo_adi = "Gıda Deposu" if st.session_state['rol'] == 'gida' else "Temizlik Deposu"

    df = verileri_getir(aktif_ws)
                        
    c_ust1, c_ust2 = st.columns([4, 1])
    with c_ust1: st.title(f"📦 {st.session_state['firma']} - {depo_adi}")
    with c_ust2:
        st.write(f"👤 {st.session_state['kullanici']}")
        if st.button("🚪 Çıkış Yap"):
            st.session_state['giris_yapildi'] = False
            st.rerun()

    try:
        dk = ws_duyuru.get_all_records()
        if dk and str(dk[0].get('Aktif', 'Hayır')) == 'Evet' and str(dk[0].get('Mesaj', '')).strip():
            st.warning(f"📢 **SİSTEM DUYURUSU:** {dk[0].get('Mesaj')}")
    except: pass

    if st.session_state['rol'] == 'admin': sekme1, sekme2, sekme3, sekme6, sekme4, sekme5, sekme7, sekme8, sekme9, sekme10, sekme11 = st.tabs(["📊 Özet & Analiz", "➕ Ürün Ekle", "🔄 Güncelle / Sil", "⚡ Hızlı İşlem", "🪪 Ürün Kartı", "📝 Geçmiş İşlemler", "📑 Sözleşmeler", "💬 Bildirimler", "👥 Kullanıcı", "📢 Duyuru", "📂 Toplu Çıkış"])
    else: sekme1, sekme2, sekme3, sekme6, sekme4, sekme5, sekme7, sekme8, sekme11 = st.tabs(["📊 Özet", "➕ Ürün Ekle", "🔄 Güncelle", "⚡ Hızlı İşlem", "🪪 Ürün Kartı", "📝 Geçmiş", "📑 Sözleşme", "💬 Bildirim", "📂 Toplu Çıkış"])

    with sekme1:
        st.markdown(f"### 📋 Uyarılar")
        krt_sayisi = 0
        for _, row in df.iterrows():
            urun, stok, miktar, birim = str(row.get('Ürün Adı', '')), str(row.get('Stok No', '')), str(row.get('Miktar', '0')), str(row.get('Birim', ''))
            try:
                skt_metni = str(row.get('SKT', ''))
                if skt_metni and skt_metni != "-" and skt_metni.lower() != "nan":
                    kalan = (datetime.strptime(skt_metni, '%Y-%m-%d').date() - datetime.now().date()).days
                    uyari = f"{urun} ({miktar} {birim})"
                    if kalan < 0:
                        st.error(f"❌ {uyari} - TARİHİ GEÇTİ! ({skt_metni})")
                        krt_sayisi += 1
                    elif 0 <= kalan <= 30:
                        st.warning(f"⚠️ {uyari} - SKT'ye {kalan} gün kaldı! ({skt_metni})")
                        krt_sayisi += 1
            except: pass
            try:
                if float(miktar) <= float(str(row.get('Kritik Stok', '10')) or '10'):
                    st.error(f"📉 STOK ALARMI: {urun} bitmek üzere! (Kalan: {float(miktar)} {birim})")
                    krt_sayisi += 1
            except: pass

        if krt_sayisi == 0: st.success("✅ Depo durumu çok iyi.")
        
        st.divider()
        st.markdown("### 🔍 Detaylı Parti Listesi")
        st.dataframe(df.drop(columns=['Resim Yolu', 'GS_Row', 'Depo Sahibi', 'Firma'], errors='ignore'), use_container_width=True, hide_index=True)

    with sekme2:
        st.subheader("Depoya Yeni Ürün Ekle")
        with st.form("urun_ekle_formu"):
            c1, c2 = st.columns(2)
            with c1:
                stok_no, urun_adi, miktar, birim, alim_turu = st.text_input("Stok No"), st.text_input("Ürün Adı"), st.number_input("Miktar", min_value=0.0), st.selectbox("Birim", ["Kg", "Litre", "Adet", "Kutu", "Paket"]), st.selectbox("Alım Türü", ["Merkezi Alım", "Piyasa Alımı"])
            with c2:
                kritik, u_tar, skt, s_no, s_tar, s_bit, s_krt = st.number_input("Kritik Seviye", value=20), st.date_input("Üretim Tarihi"), st.date_input("SKT"), st.text_input("Sözleşme No"), st.date_input("Sözleşme Tarihi"), st.date_input("Sözleşme Bitiş"), st.number_input("Sözleşme Kritik", value=20.0)
            if st.form_submit_button("Ürünü Kaydet", use_container_width=True):
                if urun_adi and stok_no:
                    yeni_satir = [len(aktif_ws.get_all_records()) + 1, stok_no, urun_adi, miktar, birim, datetime.now().strftime("%Y-%m-%d"), str(skt), str(u_tar), datetime.now().strftime("%Y-%m-%d"), "", kritik, alim_turu, s_no if alim_turu=="Piyasa Alımı" else "-", str(s_tar) if alim_turu=="Piyasa Alımı" else "-", str(s_bit) if alim_turu=="Piyasa Alımı" else "-", s_krt if alim_turu=="Piyasa Alımı" else 0.0, st.session_state['firma']]
                    satir_tam = yeni_satir + [""] * max(0, len(aktif_ws.row_values(1)) - len(yeni_satir))
                    aktif_ws.append_row(satir_tam[:len(aktif_ws.row_values(1))])
                    log_kaydet(st.session_state['kullanici'], "YENİ KAYIT", urun_adi, miktar, f"{alim_turu} ile eklendi")
                    st.success("✅ Ürün kaydedildi!")
                    st.cache_resource.clear()
                    st.rerun()
                else: st.error("Stok No ve Ürün Adı zorunludur.")

    with sekme3:
        st.subheader("🔄 Ürün Güncelle / Sil")
        if not df.empty:
            secilen = st.selectbox("İşlem yapılacak ürünü seçin:", df['ID'].astype(str) + " - " + df['Ürün Adı'])
            urun = df[df['ID'] == int(secilen.split(" - ")[0])].iloc[0]
            with st.form("guncelleme_formu"):
                c1, c2 = st.columns(2)
                with c1: 
                    yeni_stok = st.text_input("Stok No:", value=str(urun.get('Stok No', '')))
                    cikis = st.number_input("➖ Çıkış:", min_value=0, max_value=int(float(urun.get('Miktar', '0'))), step=1)
                    giris = st.number_input("➕ Giriş:", min_value=0, step=1)
                with c2: 
                    try: skt_v = datetime.strptime(str(urun.get('SKT', '')).strip(), '%Y-%m-%d').date()
                    except: skt_v = datetime.now().date()
                    y_skt = st.date_input("SKT:", value=skt_v)
                cb1, cb2 = st.columns(2)
                if cb1.form_submit_button("💾 Güncelle", type="primary"):
                    aktif_ws.update_cell(int(urun['GS_Row']), 2, yeni_stok)
                    aktif_ws.update_cell(int(urun['GS_Row']), 4, int(float(urun.get('Miktar', '0'))) - cikis + giris)
                    if cikis > 0: log_kaydet(st.session_state['kullanici'], "ÇIKIŞ", urun['Ürün Adı'], cikis, "Manuel")
                    if giris > 0: log_kaydet(st.session_state['kullanici'], "GİRİŞ", urun['Ürün Adı'], giris, "Manuel")
                    st.success("Güncellendi!")
                    st.cache_resource.clear()
                    st.rerun()
                if cb2.form_submit_button("🗑️ Sil"):
                    aktif_ws.delete_rows(int(urun['GS_Row']))
                    st.success("Silindi!")
                    st.cache_resource.clear()
                    st.rerun()

    with sekme6:
        st.subheader("⚡ Hızlı İşlem (Barkod)")
        aranan = st.text_input("🔍 Stok Numarasını Yazın:")
        if aranan:
            eslesen = df[df['Stok No'].astype(str).str.strip() == str(aranan).strip()]
            if not eslesen.empty:
                st.info(f"📦 Ürün: {eslesen.iloc[0]['Ürün Adı']} (Mevcut: {eslesen.iloc[0]['Miktar']})")
                with st.form("hizli"):
                    m_dus, m_ekle = st.number_input("➖ Çıkar:", min_value=0, step=1), st.number_input("➕ Ekle:", min_value=0, step=1)
                    if st.form_submit_button("💾 Güncelle", type="primary"):
                        if m_dus > 0 or m_ekle > 0:
                            aktif_ws.update_cell(int(eslesen.iloc[0]['GS_Row']), 4, int(eslesen.iloc[0]['Miktar']) - m_dus + m_ekle)
                            if m_dus > 0: log_kaydet(st.session_state['kullanici'], "ÇIKIŞ", eslesen.iloc[0]['Ürün Adı'], m_dus, "Hızlı")
                            st.success("Güncellendi!")
                            st.cache_resource.clear()
                            st.rerun()

    with sekme4:
        st.subheader("🪪 Ürün Kartı")
        if not df.empty:
            secilen = st.selectbox("Kart:", df['ID'].astype(str) + " - " + df['Ürün Adı'])
            ub = df[df['ID'] == int(secilen.split(" - ")[0])].iloc[0]
            st.image(qr_olustur(f"Ürün: {ub['Ürün Adı']}\nStok No: {ub['Stok No']}\nMiktar: {ub['Miktar']}"), caption="QR Kod")

    with sekme5:
        st.subheader("📝 Geçmiş")
        st.dataframe(hareketleri_getir(), use_container_width=True, hide_index=True)

    with sekme7:
        st.subheader("📑 Sözleşmeler")
        if 'Alım Türü' in df.columns:
            st.dataframe(df[df['Alım Türü'] == 'Piyasa Alımı'][['Sözleşme No', 'Ürün Adı', 'Miktar', 'Sözleşme Bitiş Tarihi']], use_container_width=True, hide_index=True)

    with sekme8:
        st.subheader("💬 Bildirim")
        with st.form("gb"):
            tur, mesaj = st.selectbox("Tür", ["Hata", "Soru"]), st.text_area("Mesaj")
            if st.form_submit_button("Gönder"):
                ws_geri_bildirim.append_row([len(ws_geri_bildirim.get_all_values()), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), st.session_state['kullanici'], tur, mesaj, st.session_state.get('firma', '')])
                st.success("İletildi!")

    if st.session_state['rol'] == 'admin':
        with sekme9:
            st.subheader("👥 Kullanıcı Yönetimi")
            with st.form("y_kullanici"):
                kadi, sifre, yetki, firma = st.text_input("K. Adı"), st.text_input("Şifre", type="password"), st.selectbox("Yetki", ["Gida", "Temizlik", "Yonetici"]), st.text_input("Firma")
                if st.form_submit_button("Kullanıcı Oluştur", type="primary") and kadi and sifre:
                    headers = kullanici_tablosu.row_values(1)
                    satir = [""] * len(headers)
                    if "Kullanıcı Adı" in headers: satir[headers.index("Kullanıcı Adı")] = kadi
                    if "Şifre" in headers: satir[headers.index("Şifre")] = sifre_hashle(sifre)
                    if "Yetki" in headers: satir[headers.index("Yetki")] = yetki
                    if "Firma" in headers: satir[headers.index("Firma")] = firma
                    if "İlk Giriş" in headers: satir[headers.index("İlk Giriş")] = "Evet"
                    kullanici_tablosu.append_row(satir)
                    st.success("Kullanıcı eklendi!")
                    st.cache_resource.clear()
        
        with sekme10:
            st.subheader("📢 Duyuru")
            with st.form("duyuru_f"):
                msg, aktif = st.text_area("Mesaj"), st.checkbox("Aktif Et")
                if st.form_submit_button("Kaydet", type="primary"):
                    if len(ws_duyuru.get_all_values()) < 2: ws_duyuru.append_row([msg, "Evet" if aktif else "Hayır"])
                    else:
                        ws_duyuru.update_cell(2, 1, msg)
                        ws_duyuru.update_cell(2, 2, "Evet" if aktif else "Hayır")
                    st.success("Duyuru güncellendi!")

    with sekme11:
        st.subheader("📂 Akıllı Toplu Çıkış İşlemi")
        giris_yontemi = st.radio("Listeyi Sisteme Nasıl Aktaracaksınız?", ["📸 Fotoğraf Çekerek (Yapay Zeka Okur)", "📥 Excel / CSV Dosyası Yükleyerek"], horizontal=True)
        df_yuklenen = None
        
        if "Fotoğraf" in giris_yontemi:
            st.info("💡 **Gelişmiş Görüntü İşleme:** Listenin fotoğrafını çekin veya yükleyin.")
            resim_dosyasi = st.file_uploader("Kamera ile çekin veya galeriden seçin", type=['jpg', 'jpeg', 'png'])
            
            if resim_dosyasi:
                if st.button("🤖 Yapay Zekaya Okut ve Tablo Oluştur", type="primary"):
                    with st.spinner("Yapay Zeka tabloyu çözümlüyor, lütfen bekleyin..."):
                        try:
                            gemini_api_key = st.secrets.get("GEMINI_API_KEY", "").strip()
                            if not gemini_api_key:
                                st.error("❌ Gemini API Anahtarı bulunamadı!")
                            else:
                                genai.configure(api_key=gemini_api_key)
                                
                                # FAZLADAN 'models/' KISMI SİLİNDİ. İŞTE DOĞRU İSİM:
                                model = genai.GenerativeModel('gemini-1.5-flash')
                                
                                prompt = """Sen uzman bir veri çıkarma asistanısın. Gönderdiğim fotoğrafta bir 'Malzeme İhtiyaç Listesi' bulunuyor. Tablodaki malzemeleri oku ve her bir satır için sadece 'Stok No' (89 ile başlayan rakamlar) ve düşülecek 'Miktar' (İhtiyaç Miktarı veya Kal. Mktr. sütunu altındaki sayılar) değerlerini çıkar. Miktarı 0 olanları yoksay. Rakamlardaki virgül formatını bozmadan olduğu gibi al. Bana SADECE geçerli bir JSON dizisi döndür, başka hiçbir metin veya markdown işareti ekleme. Örnek Format: [{"Stok No": "8920270048540", "Miktar": "25"}]"""
                                img = Image.open(resim_dosyasi)
                                
                                response = model.generate_content([prompt, img])
                                
                                json_text = response.text.strip()
                                if json_text.startswith("```json"):
                                    json_text = json_text.replace("```json", "").replace("```", "").strip()
                                elif json_text.startswith("```"):
                                    json_text = json_text.replace("```", "").strip()
                                    
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

        if df_yuklenen is not None and not df_yuklenen.empty:
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
                            onay_listesi.append({'Stok No': aranan_stok, 'Ürün Adı': eslesen.iloc[0]['Ürün Adı'], 'İşlem SKT': eslesen.iloc[0]['SKT'], 'Mevcut Stok': mevcut, 'Çıkış Miktarı': dusulecek, 'Kalan Stok': mevcut - dusulecek, 'Durum': "✅ Uygun" if mevcut - dusulecek >= 0 else "⚠️ Yetersiz", 'GS_Row': int(eslesen.iloc[0]['GS_Row'])})
                        else: hatalar.append(f"❌ {aranan_stok} stok no bulunamadı.")
                            
                if onay_listesi:
                    st.markdown("### 🔍 Düzenleme Tablosu")
                    if hatalar:
                        with st.expander("⚠️ Bulunamayanlar"):
                            for h in hatalar: st.write(h)
                    
                    with st.form("toplu_onay_formu"):
                        duzenlenmis_df = st.data_editor(pd.DataFrame(onay_listesi), column_config={"Çıkış Miktarı": st.column_config.NumberColumn("✏️ Çıkış Miktarı", min_value=0.0, step=1.0), "GS_Row": None}, disabled=["Stok No", "Ürün Adı", "İşlem SKT", "Mevcut Stok", "Kalan Stok", "Durum"], hide_index=True, use_container_width=True)
                        if st.form_submit_button("💾 Onayla ve Düş", type="primary"):
                            g_updates, log_satirlari = [], []
                            zaman, k_adi, f_adi = datetime.now().strftime('%Y-%m-%d %H:%M:%S'), st.session_state['kullanici'], st.session_state.get('firma', '')
                            mevcut_id = len(ws_hareket.get_all_values())
                            for i, r in duzenlenmis_df.iterrows():
                                g_cik = float(r['Çıkış Miktarı'])
                                if g_cik > 0:
                                    g_updates.append({'range': f"D{r['GS_Row']}", 'values': [[float(r['Mevcut Stok']) - g_cik]]})
                                    log_satirlari.append([mevcut_id + i, zaman, k_adi, "ÇIKIŞ", f"{r['Ürün Adı']} (SKT: {r['İşlem SKT']})", g_cik, "Toplu Çıkış", f_adi])
                            
                            if g_updates:
                                aktif_ws.batch_update(g_updates)
                                ws_hareket.append_rows(log_satirlari)
                                st.session_state['ai_okunan_df'] = None
                                st.success("✅ Liste başarıyla düşüldü!")
                                st.cache_resource.clear()
                                st.rerun()
