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

cursor_y = 0

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        if self.page_no() == 1:
            self.image("/home/basan/internship-codes/letterhead.png",0,0,210)
            self.image("/home/basan/internship-codes/ibmlogo.png", 170, 20, 25)
        else:
            self.image("/home/basan/internship-codes/ibmlogo.png", 183, 20, 15)
        self.set_line_width(1)
        self.ln(10)

    def add_small_title(self, text):
        global cursor_y

        if cursor_y+100>210:
            cursor_y = 30
            self.add_page()
        
        self.set_y(cursor_y)
        self.set_font("Arial", size=10)
        self.ln(10)
        self.cell(w=0, h=6, txt=text, ln=4, align='L')

        cursor_y+=20

    def add_titre(self, name, day):
        global cursor_y
        self.set_font("Arial", size = 24)
        self.ln(35)
        self.cell(w=0, txt = name+ " CPU Report", ln = 5, align = 'L')
        self.set_font("Arial", size = 15)
        self.ln(10)
        self.cell(w=0, txt = f'{day}', ln = 4, align = 'L')

        cursor_y = 67.75
        # 24pt + 35mm + 5mm + 15pt + 10mm + 4mm =
        # 39pt + 54mm
        # 67.7584 from top

    def footer(self):
        self.image("/home/basan/internship-codes/altheader.png", 0, 285, WIDTH)
        self.set_y(-8)
        self.set_font("Arial", size = 16)
        self.cell(w= 0, h=0, txt = str(self.page_no()) + '        ', ln = 3, align = 'R')

    def add_two_figures(self, figure1, figure2):
        global cursor_y
        # assuming fig sizes are 640x480
        fig_w = 640
        fig_h = 480

        new_w = 100 # width/2 -5
        new_h = (fig_h/fig_w)*new_w

        if cursor_y + new_h > HEIGHT:
            self.add_page()
            cursor_y = 30

        self.image(figure1, 5, cursor_y, new_w)
        self.image(figure2, 5+new_w, cursor_y, new_w)

        cursor_y += new_h

        if cursor_y > 290: # if out of bounds
            cursor_y = 30
            self.add_page()
    
    def add_single_figure(self, figure):
        global cursor_y
        # assuming fig size for single figure is 1000x350
        fig_w = 1000
        fig_h = 350
        new_w = 210 # WIDTH
        new_h = (fig_h/fig_w)*new_w
        if cursor_y + new_h > HEIGHT:
            self.add_page()
            cursor_y = 30
        self.image(figure, 0, cursor_y, new_w)
        cursor_y += new_h
        if cursor_y > 290:
            cursor_y = 30
            self.add_page()

    def print_chapter(self, num, title, name):
        self.add_page()
        self.chapter_title(num, title)
        self.chapter_body(name)

    def add_info(self, text):
        global cursor_y
        self.set_y(cursor_y)
        self.set_font("Arial", size = 11)
        self.ln(5)
        self.cell(w=0, txt = text, ln = 2, align = 'L')
        # 15pt + 14 mm
        # 5.2917 + 14
        # 19.2917
        cursor_y += 4
        if cursor_y > 290:
            cursor_y = 30
            self.add_page()

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

    def page_for_every_host(self, pdf):
        for host in self.client.hostnames:
            pdf.add_small_title("Charts for "+self.client.client_name+" with host "+host)
            title = "Hourly CPU Usage for " + self.client.client_name + " with host " + host
            title2 = "Weekly CPU Usage for " + self.client.client_name + " with host " + host
            title3 = "Monthly CPU Usage for " + self.client.client_name + " with host " + host
            path = "charts/"+self.client.client_name+host+'.jpg'
            path2 = "charts/weekly"+self.client.client_name+host+'.jpg'
            path3 = "charts/monthly"+self.client.client_name+host+'.jpg'
            pdf.add_two_figures(path, path2)
            pdf.add_single_figure(path3)
            pdf.ln(10)
            pdf.add_info("Average CPU usage in 1 month: ")
            pdf.add_info("Average CPU usage in 1 week: ")
            pdf.add_info("Average CPU usage in 1 week: ")
            
    def create_pdf(self):
        pdf = PDF()
        pdf.add_page()
        pdf.add_titre(self.client.client_name, "07/09/2021")
        self.page_for_every_host(pdf)
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

    def monthly_line_chart(self, title, df, hostname, clientname):
        plt.clf()
        client_days = df.select(dayofmonth('HR_Time')).distinct().orderBy('dayofmonth(HR_Time)')
        #empty arrays to be filled (will be used in matplotlib graphs)
        x = []
        y = []
        temp = []
        hours = 24
        
        for aday in client_days.collect():
            x.append(aday[0]) #insert hour names into array to be used in x axis
            #her saat icin avg processor time columni topla
            df_for_day = df.filter(dayofmonth('HR_Time') == lit(aday[0])).groupBy().sum('AVG_%_Processor_Time')
            temp.append(df_for_day.toPandas()["sum(AVG_%_Processor_Time)"].values.tolist())
            
        for i in range(0,len(temp)):
            y.append(temp[i][0])
            
        y1 = [value / hours for value in y]
            
        plt.rcParams['axes.edgecolor']='#333F4B'
        plt.rcParams['axes.linewidth']=0.8
        plt.rcParams['xtick.color']='#333F4B'
        plt.rcParams['ytick.color']='#333F4B'
    
        plt.xticks(x)
        plt.title(title)
        plt.plot(x,y1)
        plt.grid(True)
        fig = plt.gcf()
        fig.set_size_inches(10,3.5)

        plt.savefig('./charts/monthly'+clientname+hostname+'.jpg')
        fig.set_size_inches(6.4,4.8, forward=True)

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
        path = "./charts/"+self.client.client_name+'allhosts.jpg'
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

    #load_to_database("/home/basan/internship-codes/busra_cpu.xlsx", "basanto")
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
