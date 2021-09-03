import matplotlib.pyplot as plt
import pyspark
from pyspark import SparkContext
from pyspark.sql import SparkSession, SQLContext, HiveContext
from pyspark.sql.functions import *
from fpdf import FPDF
from PIL import Image
import glob
import matplotlib.cm as cm
import numpy as np

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
class ClientReport:
    def __init__(self, client):

        #client object will be passed and graphs related to that client will be printed as a seperate pdf.
        self.client = client

        self.chart_row = 1
        self.figure_num = 0
        self.page_num = 1
        self.minus = 0
        self.figure_per_page_num = 0

        self.create_pdf()

    def add_figure(self, path, pdf, width, is_last):

        if(self.figure_num % 2 == 0 or width > WIDTH/2-5):
            
            if(width > WIDTH/2-5):
                pdf.image(path, 40, 80*self.chart_row-self.minus, width)
                self.figure_num += 2
                self.figure_per_page_num +=2
            else:
                pdf.image(path, 5, 80*self.chart_row-self.minus, width)
                self.figure_per_page_num += 1
                self.figure_num += 1
            #self.y = 80*chart_row-minus
            #self.x = WIDTH/2+5
        else:
            pdf.image(path, WIDTH/2+5, 80*self.chart_row-self.minus, width)
            self.figure_per_page_num +=1
            self.chart_row += 1
            self.figure_num += 1
            #self.y = 80*self.chart_row-self.minus
            #self.x = 5
        
        if (not is_last):
            if(self.page_num > 1 and self.figure_per_page_num == 6):
                pdf.add_page()
                self.footer(pdf)
                self.line_header(pdf)
                self.figure_per_page_num = 0
                self.chart_row = 1
                self.page_num += 1

            elif(self.page_num == 1 and self.figure_per_page_num == 4):
                pdf.add_page()
                self.footer(pdf)
                self.line_header(pdf)
                self.figure_per_page_num = 0
                self.chart_row = 1
                self.page_num += 1
                self.minus = 50


    def usage_for_every_host(self, pdf):
        i = 0
        is_last = False
        for host in self.client.hostnames:
            i+=1
            if(i == len(self.client.hostnames)):
                is_last == True
            # if(self.page_num == 1):
            #     offset = self.chart_row*50
            # else:
            offset = 75
            if(self.figure_per_page_num==0 and self.page_num > 1):
                offset = 23
            elif(self.figure_per_page_num != 0):
                offset += 7

            #pdf.cell(w=0, txt = "Charts for host "+host, ln = 1, align = 'L')
            pdf.ln(offset)
            pdf.set_font('Arial', '',10)
            pdf.write(3,"            Charts for host "+host);
            title = "Hourly CPU Usage for " + self.client.client_name + " with host " + host
            title2 = "Weekly CPU Usage for " + self.client.client_name + " with host " + host
            self.hourly_line_chart(title, self.client.hosts_dataframes[host], host, self.client.client_name)
            self.weekly_bar_chart(title2, self.client.hosts_dataframes[host], host, self.client.client_name)
            path = "/home/basan/internship-codes/charts/"+self.client.client_name+host+'.jpg'
            path2 = "/home/basan/internship-codes/charts/weekly"+self.client.client_name+host+'.jpg'
            width = WIDTH/2-5
            self.add_figure(path, pdf, width, is_last)
            self.add_figure(path2, pdf, width, is_last)
            

    #function for PDF output.
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
        pdf.set_margins(13,0,0)
        day = "01/09/2021"
        self.traingle_header(pdf, day)
        self.footer(pdf)
        #pdf.set_auto_page_break(True)
        self.usage_for_every_host(pdf)
        path, width = self.all_hosts_pie_chart(pdf)
        self.add_figure(path, pdf, width, True)
        
        pdf.output("cpu-reports/" + self.client.client_name+"-example1.pdf")   

    #a chart that shows weekly CPU usage for an host of a single client. (7 days)
    #Hangi gunler daha cok kullanilmis
    def weekly_bar_chart(self, title, df, hostname, clientname):
        plt.clf()
        client_days = df.select(dayofweek('HR_Time')).distinct().orderBy('dayofweek(HR_Time)')
        #empty arrays to be filled (will be used in matplotlib graphs)
        labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        x =[]
        y = []
        temp = []
        weeks = 4*24
        
        for aday in client_days.collect():
            x.append(aday[0])
            #her saat icin avg processor time columni topla
            df_for_day = df.filter(dayofweek('HR_Time') == lit(aday[0])).groupBy().sum('AVG_%_Processor_Time')
            temp.append(df_for_day.toPandas()["sum(AVG_%_Processor_Time)"].values.tolist())
            
        for i in range(0,len(temp)):
            y.append(temp[i][0])
            
        y1 = [value / weeks for value in y]
            
        plt.rcParams['axes.edgecolor']='#333F4B'
        plt.rcParams['axes.linewidth']=0.8
        plt.rcParams['xtick.color']='#333F4B'
        plt.rcParams['ytick.color']='#333F4B'
    
        plt.xticks(x, labels)
        plt.title(title)
        plt.bar(x,y1,color=(0.2, 0.4, 0.6, 0.6))
        #ax = sns.barplot(y= "Deaths", x = "Causes", data = deaths_pd, palette=("Blues_d"))
        #sns.set_context("poster")
        plt.savefig('./charts/weekly'+clientname+hostname+'.jpg')
    
    #a chart that shows hourly CPU usage for an host of a single client (24 hours).
    #Hangi saatler daha cok kullanilmis
    def hourly_line_chart(self, title, df, hostname, clientname):
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

    #a chart that shows total percentage usage of CPU of every host
    #Hangi host daha cok kullanmis
    def all_hosts_pie_chart(self, pdf):
        plt.clf()
        labels = self.client.hostnames
        sizes = []
        d2_sizes = []
        for host in self.client.hostnames:
            df = self.client.hosts_dataframes[host].select('AVG_%_Processor_Time').groupBy().sum()
            d2_sizes.append(df.toPandas()["sum(AVG_%_Processor_Time)"].values.tolist())
        
        for i in range(0,len(d2_sizes)):
            sizes.append(d2_sizes[i][0])

        #fig1, ax1 = plt.subplots(figsize=(3, 3))
        #fig1, ax1 = plt.subplots()
        #fig1.subplots_adjust(0.1,0,1,1)

        colors = cm.rainbow(np.linspace(0, 1, len(sizes)))
        plt.gca().axis("equal")
        plt.pie(sizes, labels=labels, colors=colors, autopct = '%1.1f%%', pctdistance=1.25, labeldistance=0.9, textprops={'fontsize': 8})
        plt.title("Total Percentage Usage per Host in 1 month")
        path = "/home/basan/internship-codes/charts/"+self.client.client_name+'allhosts.jpg'
        #legend_labels = ['%s, %1.1f %%' % (l, s) for l, s in zip(labels, sizes)]
        #plt.legend(pie[0], labels=labels, bbox_to_anchor=(0.5,0.5), loc='center right', fontsize=8)
        #plt.subplots_adjust(left=0.1, bottom=0.1, right=0.11)
        plt.savefig(path)
        width = 3*WIDTH/5
        return path, width
        
class OverallReport:
    def __init__(self, dataframe):
        self.dataframe = dataframe

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

        fig1, ax1 = plt.subplots(figsize=(3, 3))
        fig1.subplots_adjust(0.1,0,1,1)

        theme = plt.get_cmap('flag')
        ax1.set_prop_cycle("color", [theme(1. * i / len(sizes)) for i in range(len(sizes))])

        ax1.pie(sizes, labels=labels, autopct='%1.1f%%', shadow=True, startangle=90, radius=100)
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
        ClientReport(client_objects[client])

    OverallReport(dataframe)
        
    