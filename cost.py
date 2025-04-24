import boto3
import json
import pandas as pd
import streamlit as st
from botocore.config import Config
import hashlib
import datetime
from typing import Dict, Tuple, Any
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# AWS 설정
AWS_REGION = 'ap-northeast-2'
BUCKET_NAME = 'project-0424'
PRICE_DB_KEY = '가격비교.db'
USER_DATA_KEY = 'users.json'

# S3 클라이언트 설정
s3_client = boto3.client(
    's3',
    region_name=AWS_REGION,
    config=Config(
        s3={'addressing_style': 'virtual'},
        signature_version='s3v4'
    )
)

# 전역 변수
user_data = {}

# 비밀번호 해싱 함수
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# S3에서 사용자 데이터 로드
def load_user_data() -> Dict:
    try:
        user_obj = s3_client.get_object(
            Bucket=BUCKET_NAME,
            Key=USER_DATA_KEY
        )
        return json.loads(user_obj['Body'].read())
    except Exception as e:
        logger.error(f"유저 데이터 로드 실패: {str(e)}")
        return {}

# S3에서 가격 데이터 로드
def load_price_data() -> pd.DataFrame:
    try:
        price_obj = s3_client.get_object(
            Bucket=BUCKET_NAME,
            Key=PRICE_DB_KEY
        )
        return pd.read_sql_table('prices', price_obj['Body'])
    except Exception as e:
        logger.error(f"가격 데이터 로드 실패: {str(e)}")
        return pd.DataFrame()

# S3에 유저 데이터 저장
def save_user_data(user_Dict) -> bool:
    try:
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=USER_DATA_KEY,
            Body=json.dumps(user_data)
        )
        logger.info("유저 데이터 저장 성공")
        return True
    except Exception as e:
        logger.error(f"유저 데이터 저장 실패: {str(e)}")
        return False

# 로그인 검증
def validate_login(username: str, password: str) -> bool:
    if not username or not password:
        return False
    
    try:
        user_data = load_user_data()
        hashed_password = hash_password(password)
        return (username in user_data and 
                user_data[username]["password"] == hashed_password)
    except Exception as e:
        logger.error(f"로그인 검증 실패: {str(e)}")
        return False

# 로그인 페이지
def login_page():
    st.title("로그인")
    
    with st.form("login_form"):
        username = st.text_input("아이디")
        password = st.text_input("비밀번호", type="password")
        submit_button = st.form_submit_button("로그인")

        if submit_button:
            if validate_login(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username
                st.success("로그인에 성공했습니다!")
                logger.info(f"사용자 로그인 성공: {username}")
                st.experimental_rerun()
            else:
                st.error("아이디 또는 비밀번호가 올바르지 않습니다.")
                logger.warning(f"로그인 실패 시도: {username}")

# 회원가입 페이지
def signup_page():
    st.title("회원가입")
    
    with st.form("signup_form"):
        new_username = st.text_input("새 아이디 (4-20자)")
        new_password = st.text_input("새 비밀번호 (8자 이상)", type="password")
        confirm_password = st.text_input("비밀번호 확인", type="password")
        submit_button = st.form_submit_button("회원가입")

        if submit_button:
            if len(new_username) < 4 or len(new_username) > 20:
                st.error("아이디는 4-20자 사이여야 합니다.")
                return

            if len(new_password) < 8:
                st.error("비밀번호는 8자 이상이어야 합니다.")
                return

            if new_password != confirm_password:
                st.error("비밀번호가 일치하지 않습니다.")
                return

            user_data = load_user_data()

            if new_username in user_data:
                st.error("이미 존재하는 아이디입니다.")
                return

            user_data[new_username] = {
                "password": hash_password(new_password),
                "created_at": str(datetime.datetime.now())
            }

            if save_user_data(user_data):
                st.success("회원가입이 완료되었습니다!")
                logger.info(f"새 사용자 등록: {new_username}")
            else:
                st.error("회원가입 중 오류가 발생했습니다.")

# 가격 검색 페이지
def search_price():
    st.title("가격 검색")

    col1, col2 = st.columns([3, 1])
    
    with col1:
        search_term = st.text_input("검색어를 입력하세요")
    
    with col2:
        sort_order = st.selectbox(
            "정렬 순서",
            ["가격 낮은순", "가격 높은순", "이름순"]
        )

    col3, col4 = st.columns(2)
    
    with col3:
        min_price = st.number_input("최소 가격", value=0)
    
    with col4:
        max_price = st.number_input("최대 가격", value=1000000)

    if st.button("검색", key="search_button"):
        price_df = load_price_data()
        
        if not price_df.empty:
            # 검색 조건 적용
            mask = (
                price_df['product_name'].str.contains(search_term, case=False, na=False) &
                (price_df['price'] >= min_price) &
                (price_df['price'] <= max_price)
            )
            filtered_df = price_df[mask]

            # 정렬 적용
            if sort_order == "가격 낮은순":
                filtered_df = filtered_df.sort_values('price')
            elif sort_order == "가격 높은순":
                filtered_df = filtered_df.sort_values('price', ascending=False)
            else:
                filtered_df = filtered_df.sort_values('product_name')

            if not filtered_df.empty:
                st.write(f"검색 결과: {len(filtered_df)}건")
                st.dataframe(
                    filtered_df.style.format({
                        'price': '{:,.0f}원',
                        'update_date': '{:%Y-%m-%d}'
                    })
                )
                logger.info(f"검색 완료: {search_term}, 결과 {len(filtered_df)}건")
            else:
                st.warning("검색 결과가 없습니다.")
                logger.info(f"검색 결과 없음: {search_term}")
        else:
            st.error("가격 데이터를 불러오는데 실패했습니다.")

# 로그아웃
def logout():
    st.session_state.logged_in = False
    st.session_state.username = None
    logger.info("사용자 로그아웃")

# 메인 앱
def main():
    st.set_page_config(
        page_title="가격 검색 서비스",
        page_icon="🛒",
        layout="wide"
    )

    # 세션 상태 초기화
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'username' not in st.session_state:
        st.session_state.username = None

    # 사이드바
    with st.sidebar:
        st.title("가격 검색 서비스")
        
        if st.session_state.logged_in:
            st.write(f"환영합니다, {st.session_state.username}님!")
            if st.button("로그아웃"):
                logout()
                st.experimental_rerun()
            
            search_price()
        else:
            tab1, tab2 = st.tabs(["로그인", "회원가입"])
            
            with tab1:
                login_page()
            
            with tab2:
                signup_page()

        # 푸터
        st.markdown("---")
        st.markdown("© 2025 가격 검색 서비스")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"애플리케이션 오류: {str(e)}")
        st.error("예기치 않은 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")