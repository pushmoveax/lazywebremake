import os
import math
print("Мы предоставляем доски 12х150см, толщиной 20,30 и 40мм.")
print("Для установки забора введите свои желаемые параметры")
price20=int(100)
price30=int(120)
price40=int(140)
#представим что участок абсолютно квадратный
area=int(input("Введите площадь своего участкa в метрах квадратных:"))
side=math.sqrt(area)
#используется округление для упрощения задач
side=round(side)
perimeter=side * 4
# Одна доска-0.12м в ширину. Это главное что нам нужно. Для измерения сколько нужно досок для забора нужно умножить perimeter на 0.12
kalitka=float(input("Введите ширину вашей калитки в метрах:"))
perimeter=perimeter-kalitka
amountoflogs=perimeter/0.12
amountoflogs=round(amountoflogs)
#для запаса +1 доска к округленному
amountoflogs=amountoflogs+1
print("Пожалуйста, выберите вид досок:")
print("1-20 мм")
print("2-30 мм")
print("3-40 мм")
while True:
    choice=input("Выберите номер:")

    if choice in ["1", "2", "3"]:
         break

    print("Неправильный номер")

if choice=="1":
    price=price20
elif choice=="2":
    price=price30
elif choice=="3":
    price=price40
total_price = amountoflogs * price
print(f"Вам нужно {amountoflogs} досок, что будет стоить {total_price} рублей. По {price} за каждую")
username=os.getlogin()
print(f"Хорошего дня,{username}")