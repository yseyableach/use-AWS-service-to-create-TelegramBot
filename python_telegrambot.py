import json
import requests

TELE_TOKEN='1806599327:AAHfTq5C08Y1DYqdaW4DH9v_DKp9lLg7YJM'
URL = "https://api.telegram.org/bot{}/".format(TELE_TOKEN)

def send_message(text, chat_id):
    final_text = "You said: " + text
    url = URL + "sendMessage?text={}&chat_id={}".format(final_text, chat_id)
    jj=requests.post(url)


#Import 套件
import json , sys, logging ,io, csv  ,boto3 ,re ,nltk
import numpy as np
import pandas as pd
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import sent_tokenize, word_tokenize
from numpy import dot
from nltk.corpus import stopwords  
from numpy.linalg import norm
from rank_bm25 import BM25Okapi

#fuck nltk
nltk.data.path.append("/tmp")
nltk.download("punkt", download_dir = "/tmp")
nltk.download("stopwords", download_dir = "/tmp")
nltk.download("wordnet", download_dir = "/tmp")

# 手動定義停用詞 ， 由於本研究為QA 問答 Which when where 應該是中藥的故保留 ， 最後加了一個q是因為我們的問句都有q開頭 這樣會產生多於比對

stop_words = set(stopwords.words('english'))  
stop_words.add("i") 
stop_words.add("q") #為了刪掉 Q:
drop_list = {"about","above","after","before","after","between",
"be","do","for","have","can","where","which","how","what","why",
"who","when","because"}
stop_words = set.difference(stop_words,drop_list)

#Load Data 將資料從s3到近來
bucket_name = 'james-bucket-nlnlouo1'
s3 = boto3.client('s3')
obj = s3.get_object(Bucket=bucket_name, Key='For_Demo_V2/all_title4.json')
all_Title = pd.read_json(io.BytesIO(obj['Body'].read())).reset_index()
obj = s3.get_object(Bucket=bucket_name, Key='For_Demo_V2/dic_for_transfer5.json')
dict_for_embedding = pd.read_json(io.BytesIO(obj['Body'].read()))
obj = s3.get_object(Bucket=bucket_name, Key='For_Demo_V2/FQA4.json')
FQA = pd.read_json(io.BytesIO(obj['Body'].read())).reset_index()

# 由於document還沒完全收完 還在整理 故先擺上來但先不回傳
obj = s3.get_object(Bucket=bucket_name, Key='For_Demo_V2/doc6.json')
doc = pd.read_json(io.BytesIO(obj['Body'].read())).reset_index()

# print(doc)

#wordnet
wtlem = WordNetLemmatizer()

#load aws service list 
obj = s3.get_object(Bucket=bucket_name, Key='ForDemo/AWS_ALL_SERVER_NEE.json')
aws_serv = pd.read_json(io.BytesIO(obj['Body'].read())).reset_index()
aws_serv = aws_serv['Service'].drop_duplicates().reset_index()['Service']
# print(aws_serv)



#計算cosine距離
def cos_sim(a,b): 
  return dot(a, b)/(norm(a)*norm(b))

#將DF句子 轉換成文字向量
def get_embedding_from_df(df): 
  vector = []
  #print(i)
  for i in df :
    #print(i)
    vector.append(get_embedding_from_single_sent(i))
  return vector

#文字預處理
def preprocess_sent(new_sent): 
  new_sent = new_sent.lower() 
  sent_stayWord = re.sub(r'[^\w\s]','',new_sent)                #去除符號 數字資料及本身已經刪除 
  corpus_tokenize = word_tokenize(sent_stayWord)
  for i in range(len(corpus_tokenize)):                                             
    corpus_tokenize[i] = wtlem.lemmatize(corpus_tokenize[i],'v')        #wordnet
  # print(corpus_tokenize)
  filtered_sentence = [w for w in corpus_tokenize if not w in stop_words]  #刪除停用詞
  return filtered_sentence

#利用索引方式取得向量
def get_embedding_from_single_sent(sent_): 
  sent_vec = []
  ti_pre = preprocess_sent(sent_)
  # print(ti_pre)
  
  for_add = np.zeros(50)
  for i in ti_pre:
    cec = list(dict_for_embedding[dict_for_embedding.vocab ==i].vector)
    # print(cec)
    if not cec :
      return "can't understand"
    else :
      for_add =np.add(for_add ,np.array(cec) )
  return for_add/len(ti_pre)
   
#去除html hash-tag   
def remove_html_tags(text): 
    """Remove html tags from a string"""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text)
    
#關鍵字搜尋分數 類似TF-IDF的方式
def get_bm25_(query_ ,df_ ,column1 ,column2):
  corpus_ = [preprocess_sent(x) for x in df_[column1]]
  query_stemmed=preprocess_sent(query_)
  bm25Model = BM25Okapi(corpus_)
  average_idf = sum(map(lambda k: float(bm25Model.idf[k]), bm25Model.idf.keys())) / len(bm25Model.idf.keys())
  scores = bm25Model.get_scores(query_stemmed)
  scores = list(scores)
  # print(max(scores))
  
  return {
      column1 : remove_html_tags(df_[column1][scores.index(max(scores))]) , 
      column2 : remove_html_tags(df_[column2][scores.index(max(scores))])
  }

# 透過tag尋找相關服務的文章
def find_keyword_DATA(question ,corpus_):
  key_word=[]
  token = word_tokenize(question)
  for serv in aws_serv:
    if(serv in token):
      key_word.append(serv)
  if not key_word or not (set(key_word).intersection(set(corpus_['Tag'].values)) ):
    return corpus_
  else: 
    return corpus_[corpus_['Tag'].isin(key_word)]
    
# 回傳主題data跟sorted cosine距離   
def get_data_distance(df_corpus ,question):
  cosine = []
  fqa_keyword = find_keyword_DATA(question ,df_corpus).reset_index(drop=True)
  # print(fqa_keyword)

  q = get_embedding_from_single_sent(question).reshape(1,50)
  for i in range(len(fqa_keyword)):
    Doc_q = np.array(fqa_keyword['Embedding'][i])
    cosine.append(cos_sim(q, Doc_q))
  sorted_cosine = sorted(cosine)
  return {"data" : fqa_keyword ,"cosine":cosine ,"sorted_cosine":sorted_cosine}

# # all_title部根據主題回傳 所以特別給他一個
def get_data_distance_all_title(df_corpus,question):
  cosine = []
  fqa_keyword = df_corpus
  q = get_embedding_from_single_sent(question).reshape(1,50)
  for i in range(len(fqa_keyword)):
    Doc_q = np.array(fqa_keyword['Embedding'][i])
    cosine.append(cos_sim(q, Doc_q))
  sorted_cosine = sorted(cosine)
  return {"data" : fqa_keyword ,"cosine":cosine ,"sorted_cosine":sorted_cosine}


#主程式
def lambda_handler(event, context):
    chat_id = event['message']['from']['id']
    
    qa = event['message']['text'].replace("cloud formation","cloudformation")
    fqa_keyword = get_data_distance(FQA ,qa)
    doc_keyword = get_data_distance(doc , qa)
    all_Title_ = get_data_distance_all_title(all_Title,qa)
    # print(remove_html_tags(fqa_keyword['data'].question[fqa_keyword['cosine'].index(fqa_keyword['sorted_cosine'][-1])]))
    
    if(type(get_embedding_from_single_sent(qa))==str):
      return "Sorry , I can't understand what you mean !"
    else :
      if(fqa_keyword['sorted_cosine'][-1] >=0.85):
          
        send_message(str(remove_html_tags(fqa_keyword['data'].question[fqa_keyword['cosine'].index(fqa_keyword['sorted_cosine'][-1])])) ,chat_id)
        send_message(str(remove_html_tags(fqa_keyword['data'].answer[fqa_keyword['cosine'].index(fqa_keyword['sorted_cosine'][-1])])) ,chat_id)
        
 
        return {
            'statusCode': 200,
            'Question': str(remove_html_tags(fqa_keyword['data'].question[fqa_keyword['cosine'].index(fqa_keyword['sorted_cosine'][-1])])),
            'Answer': str(remove_html_tags(fqa_keyword['data'].answer[fqa_keyword['cosine'].index(fqa_keyword['sorted_cosine'][-1])]).replace("A:"," ")) ,
            'url_1_title' : all_Title.Title[all_Title_['cosine'].index(all_Title_['sorted_cosine'][-1])] ,
            'url_1_url' : all_Title.url[all_Title_['cosine'].index(all_Title_['sorted_cosine'][-1])],
            
            'url_2_title' : all_Title.Title[all_Title_['cosine'].index(all_Title_['sorted_cosine'][-2])] ,
            'url_2_url' : all_Title.url[all_Title_['cosine'].index(all_Title_['sorted_cosine'][-2])],
            
            "doc_1_title" :  doc_keyword['data'].Title[doc_keyword['cosine'].index(doc_keyword['sorted_cosine'][-1])],
            "doc_1_url" :doc_keyword['data'].url[doc_keyword['cosine'].index(doc_keyword['sorted_cosine'][-1])],
            
            "doc_2_title" : doc_keyword['data'].Title[doc_keyword['cosine'].index(doc_keyword['sorted_cosine'][-2])],
            "doc_2_url" : doc_keyword['data'].url[doc_keyword['cosine'].index(doc_keyword['sorted_cosine'][-2])]
            
        }
      else : 
        bm25_title = get_bm25_(qa , all_Title ,'Title' ,'url')
        bm25_qa  = get_bm25_(qa , FQA ,'question' ,'answer')
        
        send_message(str(remove_html_tags(fqa_keyword['data'].question[fqa_keyword['cosine'].index(fqa_keyword['sorted_cosine'][-1])])) ,chat_id)
        send_message(str(remove_html_tags(fqa_keyword['data'].answer[fqa_keyword['cosine'].index(fqa_keyword['sorted_cosine'][-1])])) ,chat_id)
        
 
        return {
          'statusCode': 200,
            'Question'    : bm25_qa['question'],
            'Answer'      : bm25_qa['answer'],
            'url_1_title' : all_Title.Title[all_Title_['cosine'].index(all_Title_['sorted_cosine'][-1])] ,
            'url_1_url' : all_Title.url[all_Title_['cosine'].index(all_Title_['sorted_cosine'][-1])],
            'url_2_title' : all_Title.Title[all_Title_['cosine'].index(all_Title_['sorted_cosine'][-2])] ,
            'url_2_url' : all_Title.url[all_Title_['cosine'].index(all_Title_['sorted_cosine'][-2])],
                        
            "doc_1_title" :  doc_keyword['data'].Title[doc_keyword['cosine'].index(doc_keyword['sorted_cosine'][-1])],
            "doc_1_url" :doc_keyword['data'].url[doc_keyword['cosine'].index(doc_keyword['sorted_cosine'][-1])],
            
            "doc_2_title" : doc_keyword['data'].Title[doc_keyword['cosine'].index(doc_keyword['sorted_cosine'][-2])],
            "doc_2_url" : doc_keyword['data'].url[doc_keyword['cosine'].index(doc_keyword['sorted_cosine'][-2])]
            
        }

'''
上一版
# q = get_embedding_from_single_sent(qa).reshape(1,50)
      # # cosine_similarity(x, y).sum()
      # cos_list =[]
      # cos_list_qa = []
      # cos_list_doc = []
      
      # for i in range(len(all_Title)) :
      #   blog = np.array(all_Title['Embedding'][i])
      #   #print(cosine_similarity(q, a))
      #   cos_list.append(cos_sim(q, blog))
        
      # fqa_keyword = find_keyword_DATA(qa , FQA)[["question",	"Embedding"	,"answer"	,"Tag"]].reset_index()
      # for i in range(len(fqa_keyword)):
      #   FQ_A = np.array(fqa_keyword['Embedding'][i])
      #   cos_list_qa.append(cos_sim(q, FQ_A))

      # sorted_cos_list  = sorted(cos_list)     #For Blog
      # sorted_cos_list_qa = sorted(cos_list_qa)   #For QA
    
      
'''




# def lambda_handler(event, context):

#     # message = json.loads(event['body'])
#     chat_id = event['message']['from']['id']
#     reply = event['message']['text']
#     send_message(reply, chat_id)
#     return {
#         'statusCode': 200
#     }


        
