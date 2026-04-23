# Import python packages.
import streamlit as st

# Write directly to the app.
st.title(f"Example Streamlit App :balloon: {st.__version__}")
st.write(
  """Replace this example with your own code!
  **And if you're new to Streamlit,** check
  out our easy-to-follow guides at
  [docs.streamlit.io](https://docs.streamlit.io).
  """
)

st.markdown("""
- :page_with_curl: [Streamlit open source documentation](https://docs.streamlit.io)
- :snowflake: [Streamlit in Snowflake documentation](https://docs.snowflake.com/en/developer-guide/streamlit/about-streamlit)
- :snowboarder: [Snowpark Session documentation](https://docs.snowflake.com/en/developer-guide/snowpark/reference/python/latest/snowpark/session)
- :books: [Demo repo with templates](https://github.com/Snowflake-Labs/snowflake-demo-streamlit)
- :memo: [Streamlit in Snowflake release notes](https://docs.snowflake.com/en/release-notes/streamlit-in-snowflake)
""")

# Use an interactive slider to get user input.
high_fives_val = st.slider(
    "Number of high-fives in Q3",
    min_value=0,
    max_value=90,
    value=60,
    help="Use this to enter the number of high-fives you gave in Q3",
)

# Create a database connection to Snowflake.
conn = st.connection("snowflake")

# Create a Snowpark session from the connection.
# This provides a few helpers on top of a standard Python connection.
# If you want to use a plain Snowflake connection instead, you can create
# one with conn.cursor().
session = conn.session()

# Create a dataframe from a query.
queried_data = session.sql("""
    SELECT *
    FROM (
        VALUES
        (50, 25, 'Q1'),
        (20, 35, 'Q2'),
        -- Note the placeholder below. We're sending the slider value
        -- as a parameter. In a more interesting application, this could be
        -- filtering data in your warehouse based on user input.
        (?, 30, 'Q3')
    ) AS mock_data(high_fives, fist_bumps, quarter)
""", [high_fives_val])

# Create a simple bar chart.
# See docs.streamlit.io for more types of charts.
st.subheader("Number of high-fives")
st.bar_chart(data=queried_data, x="QUARTER", y="HIGH_FIVES")

# Alternately, render the dataframe as a table.
st.subheader("Underlying data")
st.dataframe(queried_data)
