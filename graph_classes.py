import matplotlib.pyplot as plt
import pyspark
from pyspark import SparkContext
from pyspark.sql import SparkSession, SQLContext, HiveContext
from pyspark.sql.functions import *
from fpdf import FPDF
from PIL import Image
import glob

import pymongo
import pandas as pd
import json

WIDTH = 210
HEIGHT = 297

#HELPER FUNCTIONS
def read_from_database(mongo_ip):
    iris = sqlC.read.format("com.mongodb.spark.sql.DefaultSource").option("uri", mongo_ip + "Iris").load()
    iris.createOrReplaceTempView("iris")
    iris = sqlC.sql("SELECT * FROM iris")
    #iris = iris.withColumn("Processor", iris["Processor"].cast("string"))
    return iris

def load_to_database(path_to_xlsx, database_name):
    client = pymongo.MongoClient("mongodb://localhost:27017") #connect to local server
    df = pd.read_excel(path_to_xlsx) #read from xlsx file
    data = df.to_dict(orient = "records") #insert data into a dictionary and choose the type of values as records
    db = client[database_name] #construct db
    db.Iris.insert_many(data) #insert data into db

#by creating RDD's manually, optimize the memory used and shorten execution time.
def create_partition(dataframe, sparkcontext):
    dataframe.repartition(6).createOrReplaceTempView('sf_view')
    sparkcontext.catalog.cacheTable('sf_view')
    dataframe = sparkcontext.table('sf_view')
    return dataframe

#Extract a dataframe for every client using _Total values for Processor
def extract_dataframes(dataframe):
    clients = dataframe.withColumn('Server_Name', dataframe['Server_Name'].substr(0, 3)).select('Server_Name').distinct().toPandas()["Server_Name"].values.tolist()
    client_dataframes = {}
    for client in clients:
        client_dataframes[client] = dataframe.filter(dataframe.Server_Name.contains(client) & dataframe.Processor.contains('_Total')) #take every row for a client which includes total processor usage data.
    return clients, client_dataframes


class Client:
    def __init__(self, client_dataframe, sparkcontext, client_name):
        self.client_dataframe = client_dataframe
        self.sparkcontext = sparkcontext

        self.client_name = client_name
        self.hostnames = self.client_dataframe.withColumn('Server_Name', self.client_dataframe['Server_Name'].substr(5, 1)).select('Server_Name').distinct().toPandas()["Server_Name"].values.tolist()
        self.hostnames = sorted(self.hostnames) #sort hostnames alphabetically
        
        self.hosts_dataframes = {} #Holds dataframes for every host of a client. Keys are hostnames.

        for host in self.hostnames:
            self.hosts_dataframes[host] = self.client_dataframe.filter(self.client_dataframe.Server_Name.contains(host)) #take every row includes the name of the host
        
        #mesaj gidiyo motor donmuyo hero kodu degmis olabilir
        
#Report template for CPU usage
class Report:
    def __init__(self, client):

        #client object will be passed and graphs related to that client will be printed as a seperate pdf.
        self.client = client
        self.create_pdf()

    def hourly_usage_for_every_host(self, pdf):

        host_num = 0
        chart_row = 1
        figure_num = 0
        page_num = 1
        minus = 0
        for host in self.client.hostnames:
            title = "Hourly CPU Usage for " + self.client.client_name + " with host " + host
            self.line_chart(title, self.client.hosts_dataframes[host], host, self.client.client_name)
            host_num += 1
            if(host_num % 2 == 1):
                pdf.image("/home/basan/internship-codes/charts/"+self.client.client_name+host+'.jpg', 5, 80*chart_row-minus, WIDTH/2-5)
                figure_num += 1
            else:
                pdf.image("/home/basan/internship-codes/charts/"+self.client.client_name+host+'.jpg', WIDTH/2+5, 80*chart_row-minus, WIDTH/2-5)
                figure_num +=1
                chart_row += 1
            
            if(page_num > 1 and figure_num == 6):
                pdf.add_page()
                self.footer(pdf)
                self.line_header(pdf)
                figure_num = 0
                chart_row = 1
                page_num += 1
        
            elif(page_num <= 1 and figure_num == 4):
                pdf.add_page()
                self.footer(pdf)
                self.line_header(pdf)
                figure_num = 0
                chart_row = 1
                page_num += 1
                minus = 50
                    

    #function for PDF output. It's blurry now but it will be fixed.
    def traingle_header(self, pdf, day):
        pdf.image("/home/basan/internship-codes/letterhead.png",0,0,WIDTH)
        pdf.image("/home/basan/internship-codes/ibmlogo.png", 170, 20, 25)
        pdf.set_font("Arial", size = 24)
        pdf.ln(35)
        pdf.cell(w=0, txt = "CPU Report", ln = 5, align = 'L')
        pdf.set_font("Arial", size = 15)
        pdf.ln(10)
        pdf.cell(w=0, txt = f'{day}', ln = 4, align = 'L')
        #pdf.cell(200, 30, txt = "Report Example 1", ln = 1, align = 'C')

    def line_header(self, pdf):
        #pdf.image("/home/basan/internship-codes/arkaheader.png",0,0,WIDTH)
        pdf.image("/home/basan/internship-codes/ibmlogo.png", 183, 20, 15)

    def footer(self, pdf):
        pdf.image("/home/basan/internship-codes/altheader.png", 0, 285, WIDTH)
        pdf.set_margins(0,0,0)
        pdf.set_y(-8.3)
        pdf.cell(w= 0, h=0, txt = str(pdf.page_no()) + '        ', ln = 3, align = 'R')
        pdf.set_y(0)

    def create_pdf(self):
        
        pdf = FPDF()
        pdf.set_auto_page_break(False, 0)
        pdf.add_page()
        day = "01/09/2021"
        self.traingle_header(pdf, day)
        self.footer(pdf)
        pdf.set_auto_page_break(True)
        self.hourly_usage_for_every_host(pdf)

        pdf.output("cpu-reports/" + self.client.client_name+"-example1.pdf")   

    #a chart that shows 24 hour CPU usage for an host of a single client.
    def draw_hourly_chart(self, title, df):
        plt.clf()
        client_hours = df.select(hour('HR_Time')).distinct().orderBy('hour(HR_Time)')
        #empty arrays to be filled (will be used in matplotlib graphs)
        x = []
        y = []
        temp = []
        days = 31
        
        for anhour in client_hours.collect():
            x.append(anhour[0]) #insert hour names into array to be used in x axis
            #her saat icin avg processor time columni topla
            df_for_hour = df.filter(hour('HR_Time') == lit(anhour[0])).groupBy().sum('AVG_%_Processor_Time')
            temp.append(df_for_hour.toPandas()["sum(AVG_%_Processor_Time)"].values.tolist())
            
        for i in range(0,len(temp)):
            y.append(temp[i][0])
            
        y1 = [value / days for value in y]
            
        plt.rcParams['axes.edgecolor']='#333F4B'
        plt.rcParams['axes.linewidth']=0.8
        plt.rcParams['xtick.color']='#333F4B'
        plt.rcParams['ytick.color']='#333F4B'
    
        plt.xticks(x)
        plt.title(title)
        plt.bar(x,y1,color=(0.2, 0.4, 0.6, 0.6))
        #ax = sns.barplot(y= "Deaths", x = "Causes", data = deaths_pd, palette=("Blues_d"))
        #sns.set_context("poster")
        plt.savefig('draw_hourly_chart.jpg')
    
    def line_chart(self, title, df, hostname, clientname):
        plt.clf()
        client_hours = df.select(hour('HR_Time')).distinct().orderBy('hour(HR_Time)')
        #empty arrays to be filled (will be used in matplotlib graphs)
        x = []
        y = []
        temp = []
        days = 31
        
        for anhour in client_hours.collect():
            x.append(anhour[0]) #insert hour names into array to be used in x axis
            #her saat icin avg processor time columni topla
            df_for_hour = df.filter(hour('HR_Time') == lit(anhour[0])).groupBy().sum('AVG_%_Processor_Time')
            temp.append(df_for_hour.toPandas()["sum(AVG_%_Processor_Time)"].values.tolist())
            
        for i in range(0,len(temp)):
            y.append(temp[i][0])
            
        y1 = [value / days for value in y]
            
        plt.rcParams['axes.edgecolor']='#333F4B'
        plt.rcParams['axes.linewidth']=0.8
        plt.rcParams['xtick.color']='#333F4B'
        plt.rcParams['ytick.color']='#333F4B'
    
        plt.xticks(x)
        plt.title(title)
        plt.plot(x,y1)
        plt.grid(True)
        plt.savefig('./charts/'+clientname+hostname+'.jpg')
        
    
    def client_usage(self):
        client_hours = []
        cli = []
        client_dataframes = []

        for i in self.clients:
            client_dataframes.append(self.dataframe.filter(self.dataframe.Server_Name.contains(i) & self.dataframe.Processor.contains('_Total')))

        for client in client_dataframes:
            df = client.select('AVG_%_Processor_Time').groupBy().sum()
            client_hours.append(df.toPandas()["sum(AVG_%_Processor_Time)"].values.tolist())

        for c in client_hours:
            cli.append(c[0])

        sizes = cli
        labels = ['aig', 'eti', 'tuv', 'aho', 'zor']

        fig1, ax1 = plt.subplots(figsize=(7, 7))
        fig1.subplots_adjust(0.1,0,1,1)

        theme = plt.get_cmap('flag')
        ax1.set_prop_cycle("color", [theme(1. * i / len(sizes)) for i in range(len(sizes))])

        ax1.pie(sizes, labels=labels, autopct='%1.1f%%', shadow=True, startangle=90, radius=10000)
        ax1.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
        plt.title("Total Client Usage")
        plt.savefig('client_usage.jpg')
        

if __name__ == "__main__":
    conf = pyspark.SparkConf().set("spark.jars.packages", "org.mongodb.spark:mongo-spark-connector_2.12:3.0.1").setMaster("local").setAppName("newApp").setAll([("spark.driver.memory", "15g"), ("spark.executer.memory", "20g")])
    sc = SparkContext(conf=conf)

    sqlC = SQLContext(sc)

    spark = SparkSession.builder \
    .master('local[*]') \
    .config("spark.driver.memory", "15g") \
    .appName('newApp') \
    .getOrCreate()

    mongo_ip = "mongodb://localhost:27017/basanto."
    iris = read_from_database(mongo_ip)
    dataframe = create_partition(iris, spark)

    clients = [] #names of clients
    client_dataframes = {} #dataframes of clients
    clients, client_dataframes = extract_dataframes(dataframe)
    client_objects = {} #dictionary of client objects

    for client in clients:
        client_objects[client] = Client(client_dataframes[client], spark, client)
        print(client)
        Report(client_objects[client])
        
    