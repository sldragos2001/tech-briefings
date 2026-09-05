#!/usr/bin/env python3
import yfinance as yf
from datetime import datetime, timedelta
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import sys

class EmailMomentumCalculator:
    def __init__(self):
        self.offensive_etfs = ["SXR8.DE", "EXUS.DE", "EIMI.L", "QDVE.DE"]
        self.defensive_etfs = ["VUCE.DE", "IB01.L", "PPFB.DE"]
        
        self.smtp_user = os.environ.get('SMTP_USER')
        self.smtp_pass = os.environ.get('SMTP_PASS')
        self.email_to = os.environ.get('EMAIL_TO')
        
        if not all([self.smtp_user, self.smtp_pass, self.email_to]):
            print("CRITICAL: Credențialele SMTP lipsesc din env!", file=sys.stderr)
            sys.exit(1)

    def fetch_all_history(self, tickers):
        """Descarcă datele pentru toate tickerele într-un singur request batch"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=420)
        
        try:
            # yf.download este mai robust împotriva blocajelor de IP
            df = yf.download(
                tickers=tickers,
                start=start_date.strftime('%Y-%m-%d'),
                end=end_date.strftime('%Y-%m-%d'),
                group_by='ticker',
                auto_adjust=False,
                threads=True,
                progress=False
            )
            return df
        except Exception as e:
            print(f"ERROR la yf.download: {e}", file=sys.stderr)
            return pd.DataFrame()

    def get_price_at_date(self, series, target_date):
        """Extrage prețul valid cel mai apropiat dinainte de target_date"""
        clean_series = series.dropna()
        if clean_series.empty:
            return None
        closest_date = clean_series.index.asof(target_date)
        if pd.notna(closest_date):
            val = clean_series.loc[closest_date]
            return float(val) if pd.notna(val) else None
        return None

    def calculate_momentum_from_series(self, ticker, close_series):
        try:
            if close_series is None or close_series.dropna().empty:
                print(f"WARNING: Date lipsă pentru {ticker}", file=sys.stderr)
                return None

            tz = close_series.index.tz
            end_date_tz = pd.Timestamp.now(tz=tz) if tz else datetime.now()

            current_price = self.get_price_at_date(close_series, end_date_tz)
            price_1m = self.get_price_at_date(close_series, end_date_tz - timedelta(days=30))
            price_3m = self.get_price_at_date(close_series, end_date_tz - timedelta(days=90))
            price_6m = self.get_price_at_date(close_series, end_date_tz - timedelta(days=180))
            price_12m = self.get_price_at_date(close_series, end_date_tz - timedelta(days=365))

            prices = [current_price, price_1m, price_3m, price_6m, price_12m]
            if all(p is not None and p > 0 for p in prices):
                momentum = (12 * (current_price / price_1m - 1)) + \
                           (4 * (current_price / price_3m - 1)) + \
                           (2 * (current_price / price_6m - 1)) + \
                           (current_price / price_12m - 1)
                return {
                    'ticker': ticker,
                    'current_price': current_price,
                    'price_1m': price_1m,
                    'price_3m': price_3m,
                    'price_6m': price_6m,
                    'price_12m': price_12m,
                    'momentum': momentum
                }
            else:
                print(f"WARNING: Prețuri incomplete pentru {ticker}: {prices}", file=sys.stderr)
        except Exception as e:
            print(f"ERROR procesare {ticker}: {e}", file=sys.stderr)
        return None

    def create_etf_table_html(self, etfs_data, title):
        html = f"""
        <h2>{title}</h2>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; margin-bottom: 20px;">
            <thead>
                <tr style="background-color: #f2f2f2;">
                    <th>Ticker</th>
                    <th>Preț Curent</th>
                    <th>1 Lună</th>
                    <th>3 Luni</th>
                    <th>6 Luni</th>
                    <th>12 Luni</th>
                    <th>Momentum</th>
                </tr>
            </thead>
            <tbody>
        """
        for etf in etfs_data:
            momentum_color = "green" if etf['momentum'] >= 0 else "red"
            html += f"""
            <tr>
                <td><strong>{etf['ticker']}</strong></td>
                <td>{etf['current_price']:.2f}</td>
                <td>{etf['price_1m']:.2f}</td>
                <td>{etf['price_3m']:.2f}</td>
                <td>{etf['price_6m']:.2f}</td>
                <td>{etf['price_12m']:.2f}</td>
                <td style="color: {momentum_color}; font-weight: bold;">{etf['momentum']:.4f}</td>
            </tr>
            """
        html += "</tbody></table>"
        return html

    def create_recommendation_html(self, offensive_data, defensive_data):
        html = """
        <h2>🎯 Recomandare de Investiție</h2>
        <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 20px 0;">
        """
        if not offensive_data or not defensive_data:
            html += "<p><strong>❌ Date insuficiente pentru o recomandare completă. Unele API-uri au eșuat.</strong></p></div>"
            return html
            
        negative_offensive_count = sum(1 for etf in offensive_data if etf['momentum'] < 0)
        best_defensive = max(defensive_data, key=lambda x: x['momentum']) if defensive_data else None
        
        html += f"""
        <p><strong>📊 Analiză:</strong></p>
        <ul>
            <li>ETF-uri ofensive cu momentum negativ: {negative_offensive_count}</li>
            <li>ETF-uri ofensive totale evaluate: {len(offensive_data)}</li>
        </ul>
        """
        if negative_offensive_count == 0:
            best_offensive = max(offensive_data, key=lambda x: x['momentum'])
            html += f"<p><strong>🚀 ACTIUNE:</strong> Toți banii în: <strong>{best_offensive['ticker']}</strong> (Momentum: {best_offensive['momentum']:.4f})</p>"
        elif negative_offensive_count == 1:
            html += f"<p><strong>⚠️ ACTIUNE:</strong> Mută 50% în defensiv: <strong>{best_defensive['ticker']}</strong> (Momentum: {best_defensive['momentum']:.4f})</p>"
        else:
            html += f"<p><strong>🛡️ ACTIUNE:</strong> Mută 100% în defensiv: <strong>{best_defensive['ticker']}</strong> (Momentum: {best_defensive['momentum']:.4f})</p>"
        
        html += "</div>"
        return html

    def create_summary_html(self, offensive_data, defensive_data):
        html = """
        <h2>📈 Sumar Statistici</h2>
        <div style="background-color: #e8f5e8; border: 1px solid #c3e6c3; padding: 15px; border-radius: 5px; margin: 20px 0;">
        """
        if offensive_data:
            avg_off = sum(e['momentum'] for e in offensive_data) / len(offensive_data)
            html += f"<p><strong>📈 ETF-uri Ofensive - Mediu:</strong> {avg_off:.4f}</p>"
        if defensive_data:
            avg_def = sum(e['momentum'] for e in defensive_data) / len(defensive_data)
            html += f"<p><strong>🛡️ ETF-uri Defensive - Mediu:</strong> {avg_def:.4f}</p>"
        html += "</div>"
        return html

    def send_email(self, html_content):
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"ETF Momentum Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        msg['From'] = self.smtp_user
        msg['To'] = self.email_to
        
        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="UTF-8"></head>
        <body style="font-family: Arial, sans-serif; margin: 20px;">
            <h1 style="color: #2c3e50; text-align: center;">🚀 ETF Momentum Tracker</h1>
            <hr>{html_content}<hr>
            <p style="text-align: center; color: #7f8c8d; font-size: 12px;">
                ⏰ Actualizat la: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </p>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_template, 'html'))
        
        try:
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(self.smtp_user, self.smtp_pass)
            server.sendmail(self.smtp_user, self.email_to, msg.as_string())
            server.quit()
            print(f"✅ Raport trimis cu succes la {self.email_to}")
        except Exception as e:
            print(f"CRITICAL: Eroare trimitere email: {e}", file=sys.stderr)
            sys.exit(1)

    def run_analysis(self):
        all_tickers = self.offensive_etfs + self.defensive_etfs
        print("🔄 Se descarcă datele în mod batch...")
        batch_df = self.fetch_all_history(all_tickers)
        
        offensive_data = []
        for ticker in self.offensive_etfs:
            series = None
            if not batch_df.empty:
                if ticker in batch_df.columns.levels[0]:
                    series = batch_df[ticker]['Close']
            data = self.calculate_momentum_from_series(ticker, series)
            if data:
                offensive_data.append(data)

        defensive_data = []
        for ticker in self.defensive_etfs:
            series = None
            if not batch_df.empty:
                if ticker in batch_df.columns.levels[0]:
                    series = batch_df[ticker]['Close']
            data = self.calculate_momentum_from_series(ticker, series)
            if data:
                defensive_data.append(data)

        html_content = ""
        html_content += self.create_etf_table_html(offensive_data, "ETF OFENSIVE")
        html_content += self.create_etf_table_html(defensive_data, "ETF DEFENSIVE")
        html_content += self.create_recommendation_html(offensive_data, defensive_data)
        html_content += self.create_summary_html(offensive_data, defensive_data)
        
        self.send_email(html_content)

if __name__ == "__main__":
    EmailMomentumCalculator().run_analysis()
