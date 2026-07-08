import requests

def main():
    print("="*50)
    print("🤖 텔레그램 Chat ID 자동 탐지기")
    print("="*50)
    token = input("\n👉 봇파더에게 받은 [토큰(Token)]을 붙여넣고 엔터를 치세요:\n(예: 123456789:ABCDefgh...)\n> ").strip()
    
    if not token:
        print("❌ 토큰이 입력되지 않았습니다.")
        return

    print("\n🔍 텔레그램 서버와 통신 중...")
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if not data.get("ok"):
            print(f"\n❌ 에러: 유효하지 않은 토큰입니다. (에러코드: {data.get('error_code')})")
            print("토큰을 처음부터 끝까지 정확히 복사했는지 확인해 주세요.")
            return
            
        results = data.get("result", [])
        if not results:
            print("\n⚠️ [기록 없음] 봇에게 도착한 메시지가 하나도 없습니다!")
            print("스마트폰 텔레그램을 열고 봇 방에 들어가서 아무 글자나 하나 전송하신 후, 이 스크립트를 다시 실행해 주세요.")
            return
            
        # 가장 최근 메시지에서 chat id 추출
        last_update = results[-1]
        chat_id = None
        
        if "message" in last_update:
            chat_id = last_update["message"]["chat"]["id"]
        elif "my_chat_member" in last_update:
            chat_id = last_update["my_chat_member"]["chat"]["id"]
            
        if chat_id:
            print("\n🎉 성공적으로 Chat ID를 찾았습니다!!!")
            print("="*50)
            print(f"✅ 대장님의 진짜 Chat ID:  {chat_id}")
            print("="*50)
            print("이 숫자 전체(마이너스가 있다면 마이너스 포함)를 복사해서 깃허브 시크릿에 넣어주세요.")
        else:
            print("\n❌ 메시지는 찾았으나 Chat ID를 추출하지 못했습니다.")
            
    except Exception as e:
        print(f"\n❌ 통신 중 오류가 발생했습니다: {e}")

if __name__ == "__main__":
    main()
