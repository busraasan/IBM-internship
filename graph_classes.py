import matplotlib.pyplot as plt
import pyspark
from pyspark import SparkContext
from pyspark.sql import SparkSession, SQLContext, HiveContext
from pyspark.sql.functions import *
from fpdf import FPDF
from PIL import Image
import glob

WIDTH = 210
HEIGHT = 297

def read_from_database(mongo_ip):

    iris = sqlC.read.format("com.mongodb.spark.sql.DefaultSource").option("uri", mongo_ip + "Iris").load()
    iris.createOrReplaceTempView("iris")
    iris = sqlC.sql("SELECT * FROM iris")
    #iris = iris.withColumn("Processor", iris["Processor"].cast("string"))
    return iris

class Client:
    def __init__(self, dataframe, sparkcontext, client_name):
        self.client_dataframe = dataframe
        self.sparkcontext = sparkcontext

        self.client = client_name
        self.hostnames = dataframe.withColumn('Server_Name', dataframe['Server_Name'].substr(0, 3)).select('Server_Name').distinct().toPandas()["Server_Name"].values.tolist()
        
        self.hosts_dataframes = {}

        for host in hostnames:
            hosts_dataframes[host] = self.dataframe[client].filter(self.dataframe[client].Server_Name.contains(host))
        

class Graphs:
    def __init__(self, dataframe, sparkcontext):

        self.dataframe = dataframe
        self.sparkcontext = sparkcontext
        self.client_dataframes = []
        self.host_dataframes = []

        self.create_partition()
        
        #extract client names from server_name
        self.clients = dataframe.withColumn('Server_Name', dataframe['Server_Name'].substr(0, 3)).select('Server_Name').distinct().toPandas()["Server_Name"].values.tolist()
        self.client_hosts = []

        #extract hostnames for each client
        for i in self.clients:
            hostnames = dataframe.filter(dataframe.Server_Name.contains(i)).withColumn('Server_Name', dataframe['Server_Name'].substr(5,1)).select('Server_Name').distinct().toPandas()["Server_Name"].values.tolist()
            self.client_hosts.append(hostnames)

        #create a dictionary stores the names of the clients and hosts of them
        self.client_data = {}
        for i in range(0, len(self.clients)):
            self.client_data[self.clients[i]] = self.client_hosts[i]

        #dictionary for dataframes
        self.host_client_dfs = {} #stores data of all clients hosts seperately as df
        self.client_dfs = {} #stores data of all clients seperately as df

        self.extract_dataframes()
        self.create_pdf()

    def extract_dataframes(self):
        for client in self.clients:
            self.client_dfs[client] = self.dataframe.filter(self.dataframe.Server_Name.contains(client) & self.dataframe.Processor.contains('_Total')) #take every row for a client which includes total processor usage data.
            for host_info in self.client_data[client]:
                self.host_dataframes.append(self.client_dfs[client].filter(self.client_dfs[client].Server_Name.contains(host_info)))
            self.host_client_dfs[client] = self.host_dataframes

    #by creating RDD's manually, optimize the memory used and shorten execution time.
    def create_partition(self):
        self.dataframe.repartition(6).createOrReplaceTempView('sf_view')
        self.sparkcontext.catalog.cacheTable('sf_view')
        self.dataframe = self.sparkcontext.table('sf_view')

    def hourly_usage_for_every_host(self, pdf):

        host_num = 0
        chart_row = 1
        figure_num = 0
        page_num = 1
        minus = 0
        for client in self.clients:
            print(client)
            for host in self.client_data[client]:
                title = "Hourly CPU Usage for " + client + " with host " + host
                self.line_chart(title, self.host_client_dfs[client][host_num], host, client)
                host_num += 1
                if(host_num % 2 == 0):
                    pdf.image("/home/basan/internship-codes/charts/"+client+host+'.jpg', 5, 80*chart_row-minus, WIDTH/2-5)
                    chart_row += 1
                    figure_num += 1
                else:
                    pdf.image("/home/basan/internship-codes/charts/"+client+host+'.jpg', WIDTH/2+5, 80*chart_row-minus, WIDTH/2-5)
                    figure_num +=1
                
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
        pdf.image("/home/basan/internship-codes/ibmlogo.png", 170, 20, 15)

    def footer(self, pdf):
        pdf.image("/home/basan/internship-codes/altheader.png", 0, 285, WIDTH)
        pdf.set_margins(0,0,0)
        pdf.set_y(-8.3)
        pdf.cell(w= 0, h=0, txt = str(pdf.page_no()) + '        ', ln = 3, align = 'R')
        pdf.set_y(0)

    def create_pdf(self):
        
        #self.draw_hourly_chart("hh")
        #self.line_chart("line chart")
        #self.client_usage()
        pdf = FPDF()
        pdf.set_auto_page_break(False, 0)
        pdf.add_page()
        day = "01/09/2021"
        self.traingle_header(pdf, day)
        self.footer(pdf)
        pdf.set_auto_page_break(True)

        self.hourly_usage_for_every_host(pdf)

        # im1 = "/home/basan/internship-codes/draw_hourly_chart.jpg"
        # im2 = "/home/basan/internship-codes/line_chart.jpg"
        # im3 = "/home/basan/internship-codes/client_usage.jpg"

        # pdf.image(im1, 5, 80, WIDTH/2-5)
        # pdf.image(im2, WIDTH/2+5, 80, WIDTH/2-5)
        # pdf.image(im3, 5, 160, WIDTH/2-5)

        # imagelist = [im1, im2, im3]
        # k = -1
        # for image in imagelist:
        #     k *= -1
        #     pdf.image(image, 5, 30, WIDTH/2+k*5)

        # save the pdf with name .pdf
        pdf.output("example1.pdf")   

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
            #her saat için avg processor time columnı topla
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
            #her saat için avg processor time columnı topla
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

    Graphs(iris, spark)
