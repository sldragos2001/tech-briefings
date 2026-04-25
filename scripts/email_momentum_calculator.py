import yfinance as yf
from datetime import datetime, timedelta
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time

class EmailMomentumCalculator:
    def __init__(self):
        self.offensive_etfs = ["SXR8.DE", "EXUS.DE", "EIMI.L", "QDVE.DE"]
        self.defensive_etfs = ["VUCE.DE", "IB01.L", "PPFB.DE"]
        self.email_to = "sldragos2001@gmail.com"
        
    def get_price_at_date(self, data, target_date):
        """Get price at specific date"""
        closest_date = data.index.asof(target_date)
        return data.loc[closest_date]['Close'] if pd.notna(closest_date) else None

    def calculate_momentum(self, ticker):
        """Calculate momentum for a given ticker"""
        try:
            stock = yf.Ticker(ticker)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=400)
            hist_data = stock.history(start=start_date.strftime('%Y-%m-%d'), 
                                    end=end_date.strftime('%Y-%m-%d'))

            if hist_data.empty:
                return None

            tz = hist_data.index.tz
            end_date_tz = pd.Timestamp.now(tz=tz) if tz else end_date

            current_price = self.get_price_at_date(hist_data, end_date_tz)
            price_1m = self.get_price_at_date(hist_data, end_date_tz - timedelta(days=30))
            price_3m = self.get_price_at_date(hist_data, end_date_tz - timedelta(days=90))
            price_6m = self.get_price_at_date(hist_data, end_date_tz - timedelta(days=180))
            price_12m = self.get_price_at_date(hist_data, end_date_tz - timedelta(days=365))

            if all(p is not None and p > 0 for p in [current_price, price_1m, price_3m, price_6m, price_12m]):
                momentum = (12 * (current_price/price_1m - 1)) + (4 * (current_price/price_3m - 1)) + \
                          (2 * (current_price/price_6m - 1)) + (current_price/price_12m - 1)
                return {
                    'ticker': ticker,
                    'current_price': current_price,
                    'price_1m': price_1m,
                    'price_3m': price_3m,
                    'price_6m': price_6m,
                    'price_12m': price_12m,
                    'momentum': momentum
                }
        except Exception as e:
            print(f"Error fetching data for {ticker}: {e}")
        return None

    def create_etf_table_html(self, etfs_data, title):
        """Create HTML table for ETF data"""
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
            if etf:
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
        
        html += """
            </tbody>
        </table>
        """
        return html

    def create_recommendation_html(self, offensive_data, defensive_data):
        """Create HTML for investment recommendation"""
        html = """
        <h2>🎯 Recomandare de Investiție</h2>
        <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 20px 0;">
        """
        
        if not offensive_data or not defensive_data:
            html += "<p><strong>❌ Date insuficiente pentru o recomandare.</strong></p>"
            html += "</div>"
            return html
            
        negative_offensive_count = sum(1 for etf in offensive_data if etf and etf['momentum'] < 0)
        best_defensive = max(defensive_data, key=lambda x: x['momentum']) if defensive_data else None
        
        html += f"""
        <p><strong>📊 Analiză:</strong></p>
        <ul>
            <li>ETF-uri ofensive cu momentum negativ: {negative_offensive_count}</li>
            <li>ETF-uri ofensive totale: {len(offensive_data)}</li>
        </ul>
        """
        
        if negative_offensive_count == 0:
            best_offensive = max(offensive_data, key=lambda x: x['momentum'])
            html += f"""
            <p><strong>🚀 ACTIUNE:</strong> Toți banii în ETF-ul ofensiv cu cel mai bun momentum: <strong>{best_offensive['ticker']}</strong></p>
            <p>Momentum: {best_offensive['momentum']:.4f}</p>
            """
        elif negative_offensive_count == 1:
            html += f"""
            <p><strong>⚠️ ACTIUNE:</strong> Mută 50% din portofoliu în activul defensiv cu cel mai bun momentum: <strong>{best_defensive['ticker']}</strong></p>
            <p>Momentum: {best_defensive['momentum']:.4f}</p>
            """
        else:
            html += f"""
            <p><strong>🛡️ ACTIUNE:</strong> Mută 100% din portofoliu în activul defensiv cu cel mai bun momentum: <strong>{best_defensive['ticker']}</strong></p>
            <p>Momentum: {best_defensive['momentum']:.4f}</p>
            """
        
        html += "</div>"
        return html

    def create_summary_html(self, offensive_data, defensive_data):
        """Create HTML for summary statistics"""
        html = """
        <h2>📈 Sumar Statistici</h2>
        <div style="background-color: #e8f5e8; border: 1px solid #c3e6c3; padding: 15px; border-radius: 5px; margin: 20px 0;">
        """
        
        if offensive_data:
            offensive_momentums = [etf['momentum'] for etf in offensive_data if etf]
            avg_offensive = sum(offensive_momentums) / len(offensive_momentums)
            html += f"<p><strong>📈 ETF-uri Ofensive - Momentum mediu:</strong> {avg_offensive:.4f}</p>"
            
        if defensive_data:
            defensive_momentums = [etf['momentum'] for etf in defensive_data if etf]
            avg_defensive = sum(defensive_momentums) / len(defensive_momentums)
            html += f"<p><strong>🛡️ ETF-uri Defensive - Momentum mediu:</strong> {avg_defensive:.4f}</p>"
        
        html += "</div>"
        return html

    def send_email(self, html_content):
        """Send email with the momentum report"""
        # Email configuration - you'll need to set these up
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        
        # ⚠️ CONFIGURARE NECESARĂ:
        # Înlocuiește cu datele tale Gmail
        sender_email = "sldragos2001@gmail.com"  # EX: "dragos@gmail.com"
        sender_password = "njhi odzd farf krby"  # EX: "abcd efgh ijkl mnop"
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"ETF Momentum Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        msg['From'] = sender_email
        msg['To'] = self.email_to
        
        # Create HTML content
        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #2c3e50; text-align: center; }}
                h2 {{ color: #34495e; border-bottom: 2px solid #3498db; padding-bottom: 5px; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
                th {{ background-color: #f2f2f2; }}
                .positive {{ color: green; font-weight: bold; }}
                .negative {{ color: red; font-weight: bold; }}
            </style>
        </head>
        <body>
            <h1>🚀 ETF Momentum Tracker</h1>
            <p style="text-align: center; color: #7f8c8d;">Analiză Momentum pentru Investiții</p>
            <hr>
            {html_content}
            <hr>
            <p style="text-align: center; color: #7f8c8d; font-size: 12px;">
                ⏰ Actualizat la: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </p>
        </body>
        </html>
        """
        
        html_part = MIMEText(html_template, 'html')
        msg.attach(html_part)
        
        try:
            # Create server connection
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(sender_email, sender_password)
            
            # Send email
            text = msg.as_string()
            server.sendmail(sender_email, self.email_to, text)
            server.quit()
            
            print(f"✅ Raportul a fost trimis cu succes la {self.email_to}")
            
        except Exception as e:
            print(f"❌ Eroare la trimiterea email-ului: {e}")
            print("\n📧 Pentru a configura email-ul:")
            print("1. Înlocuiește 'your_email@gmail.com' cu adresa ta Gmail")
            print("2. Înlocuiește 'your_app_password' cu parola de aplicație Gmail")
            print("3. Activează autentificarea cu 2 factori în Gmail")
            print("4. Generează o parolă de aplicație în setările Gmail")

    def run_analysis(self):
        """Run the complete momentum analysis and send email"""
        print("🔄 Se încarcă datele...")
        
        # Fetch offensive ETFs data
        offensive_data = []
        for ticker in self.offensive_etfs:
            print(f"   📊 Se analizează {ticker}...")
            data = self.calculate_momentum(ticker)
            offensive_data.append(data)
            time.sleep(0.5)
            
        # Fetch defensive ETFs data
        defensive_data = []
        for ticker in self.defensive_etfs:
            print(f"   📊 Se analizează {ticker}...")
            data = self.calculate_momentum(ticker)
            defensive_data.append(data)
            time.sleep(0.5)
            
        print("📧 Se generează raportul HTML...")
        
        # Create HTML content
        html_content = ""
        html_content += self.create_etf_table_html(offensive_data, "ETF OFENSIVE")
        html_content += self.create_etf_table_html(defensive_data, "ETF DEFENSIVE")
        html_content += self.create_recommendation_html(offensive_data, defensive_data)
        html_content += self.create_summary_html(offensive_data, defensive_data)
        
        # Send email
        self.send_email(html_content)

def main():
    """Main function"""
    calculator = EmailMomentumCalculator()
    calculator.run_analysis()

if __name__ == "__main__":
    main() 
