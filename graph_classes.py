import matplotlib.pyplot as plt
import pyspark
from pyspark import SparkContext
from pyspark.sql import SparkSession, SQLContext, HiveContext
from pyspark.sql.functions import *
from fpdf import FPDF
from PIL import Image
import glob

def read_from_database(mongo_ip):

    iris = sqlC.read.format("com.mongodb.spark.sql.DefaultSource").option("uri", mongo_ip + "Iris").load()
    iris.createOrReplaceTempView("iris")
    iris = sqlC.sql("SELECT * FROM iris")
    return iris

class Graphs:
    def __init__(self, dataframe, sparkcontext):

        self.dataframe = dataframe
        self.sparkcontext = sparkcontext

        self.create_partition()
        
        #extract client names from server_name
        self.clients = dataframe.withColumn('Server_Name', iris['Server_Name'].substr(0, 3)).select('Server_Name').distinct().toPandas()["Server_Name"].values.tolist()
        self.allhosts = []

        #extract hostnames for each client
        for i in self.clients:
            hostnames = dataframe.filter(dataframe.Server_Name.contains(i)).withColumn('Server_Name', iris['Server_Name'].substr(5,1)).select('Server_Name').distinct().toPandas()["Server_Name"].values.tolist()
            self.allhosts.append(hostnames)

        #create a dictionary for the sake of the ease of understanding
        self.client_data = {}
        for i in range(0, len(self.clients)):
            self.client_data[self.clients[i]] = self.allhosts[i]

        self.create_pdf()

    #by creating RDD's manually, optimize the memory used and shorten execution time.
    def create_partition(self):
        self.dataframe.repartition(6).createOrReplaceTempView('sf_view')
        self.sparkcontext.catalog.cacheTable('sf_view')
        self.dataframe = self.sparkcontext.table('sf_view')

    #function for PDF output. It's blurry now but it will be fixed.
    def create_pdf(self):
        self.draw_hourly_chart("draw hourly chart")
        self.line_chart("line chart")
        self.client_usage()

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size = 15)
        pdf.cell(200, 10, txt = "Report Example 1", ln = 1, align = 'C')

        im1 = "/home/basan/internship-codes/draw_hourly_chart.jpg"
        im2 = "/home/basan/internship-codes/line_chart.jpg"
        im3 = "/home/basan/internship-codes/client_usage.jpg"

        imagelist = [im1, im2, im3]

        for image in imagelist:
            pdf.image(image, w=100, h=70)

        # save the pdf with name .pdf
        pdf.output("example1.pdf")   

    #a chart that shows 24 hour CPU usage for an host of a single client.
    def draw_hourly_chart(self, title):
        plt.clf()
        client_hours = self.dataframe.select(hour('HR_Time')).distinct().orderBy('hour(HR_Time)')
        #empty arrays to be filled (will be used in matplotlib graphs)
        x = []
        y = []
        temp = []
        days = 31
        
        for anhour in client_hours.collect():
            x.append(anhour[0]) #insert hour names into array to be used in x axis
            #her saat için avg processor time columnı topla
            df_for_hour = self.dataframe.filter(hour('HR_Time') == lit(anhour[0])).groupBy().sum('AVG_%_Processor_Time')
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
    
    def line_chart(self, title):
        plt.clf()
        client_hours = self.dataframe.select(hour('HR_Time')).distinct().orderBy('hour(HR_Time)')
        #empty arrays to be filled (will be used in matplotlib graphs)
        x = []
        y = []
        temp = []
        days = 31
        
        for anhour in client_hours.collect():
            x.append(anhour[0]) #insert hour names into array to be used in x axis
            #her saat için avg processor time columnı topla
            df_for_hour = self.dataframe.filter(hour('HR_Time') == lit(anhour[0])).groupBy().sum('AVG_%_Processor_Time')
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
        plt.savefig('line_chart.jpg')
        
    
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


    mongo_ip = "mongodb://localhost:27017/basan-son-data."
    iris = read_from_database(mongo_ip)

    Graphs(iris, spark)
